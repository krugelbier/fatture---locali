# XML & P7M File Importer with duplicate prevention and automatic assignment
import json
import sqlite3
import zipfile
import io
import os
from typing import Dict, Any, List, Tuple
from app.services.importer.base import InvoiceImportProvider
from app.services.xml_parser import FatturaPAParser
from app.services.assignment_engine import AssignmentEngine

class XmlFileImporter(InvoiceImportProvider):
    def get_provider_name(self) -> str:
        return "Importazione Manuale XML / P7M / ZIP"

    def test_connection(self) -> Dict[str, Any]:
        return {"status": "OK", "message": "Importatore file XML e archivi ZIP pronto all'uso"}

    @classmethod
    def process_zip_bytes(cls, conn: sqlite3.Connection, zip_bytes: bytes, zip_filename: str) -> Dict[str, Any]:
        """
        Decomprime un archivio ZIP in memoria ed elabora tutte le fatture XML / P7M
        in esso contenute (anche in sottocartelle), gestendo duplicati e statistiche.
        """
        results = []
        imported = 0
        duplicates = 0
        errors = 0
        total_extracted = 0

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                for member in zf.infolist():
                    # Ignora cartelle e file di sistema macOS
                    if member.is_dir() or member.filename.startswith("__MACOSX/") or "/." in member.filename or member.filename.startswith("."):
                        continue
                    
                    fname_lower = member.filename.lower()
                    
                    # File XML o P7M
                    if fname_lower.endswith(".xml") or fname_lower.endswith(".p7m"):
                        total_extracted += 1
                        file_data = zf.read(member.filename)
                        base_name = os.path.basename(member.filename)
                        
                        try:
                            res = cls.process_file_bytes(conn, file_data, base_name)
                            results.append(res)
                            if res.get("is_duplicate"):
                                duplicates += 1
                            elif res.get("success"):
                                imported += 1
                            else:
                                errors += 1
                        except Exception as e:
                            errors += 1
                            results.append({
                                "filename": base_name,
                                "success": False,
                                "is_duplicate": False,
                                "message": f"Errore nell'elaborazione del file estratto {base_name}: {str(e)}"
                            })
                    
                    # Supporto anche per zip annidati (zip dentro zip)
                    elif fname_lower.endswith(".zip"):
                        nested_zip_bytes = zf.read(member.filename)
                        nested_res = cls.process_zip_bytes(conn, nested_zip_bytes, os.path.basename(member.filename))
                        imported += nested_res.get("imported", 0)
                        duplicates += nested_res.get("duplicates", 0)
                        errors += nested_res.get("errors", 0)
                        total_extracted += nested_res.get("total_xml_found", 0)
                        results.extend(nested_res.get("details", []))

        except zipfile.BadZipFile:
            return {
                "success": False,
                "filename": zip_filename,
                "message": f"Il file {zip_filename} non è un archivio ZIP valido o risulta corrotto."
            }
        except Exception as e:
            return {
                "success": False,
                "filename": zip_filename,
                "message": f"Errore durante l'apertura dello ZIP {zip_filename}: {str(e)}"
            }

        return {
            "success": True,
            "is_zip": True,
            "filename": zip_filename,
            "total_xml_found": total_extracted,
            "imported": imported,
            "duplicates": duplicates,
            "errors": errors,
            "message": f"Archivio ZIP '{zip_filename}' elaborato: {imported} fatture importate, {duplicates} duplicati ignorati.",
            "details": results
        }

    @classmethod
    def process_file_bytes(cls, conn: sqlite3.Connection, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Elabora un singolo file XML o P7M, controlla i duplicati,
        valuta le sedi, mappa i prodotti e salva nel database.
        """
        cursor = conn.cursor()

        # 1. Parsing dell'XML
        parsed = FatturaPAParser.parse_file(file_bytes, filename)
        file_hash = parsed["file_hash"]
        num_doc = parsed["numero_documento"]
        data_doc = parsed["data_documento"]
        piva_cedente = parsed["cedente_piva"]

        # 2. Controllo duplicati:
        # A) Per hash univoco del file
        cursor.execute("SELECT id, filename, numero_documento FROM documenti WHERE file_hash = ?", (file_hash,))
        dup_by_hash = cursor.fetchone()
        if dup_by_hash:
            return {
                "success": False,
                "is_duplicate": True,
                "documento_id": dup_by_hash["id"],
                "numero_documento": dup_by_hash["numero_documento"],
                "message": f"Fattura già presente nel sistema (ID {dup_by_hash['id']}, file: {dup_by_hash['filename']}). Importazione ignorata per evitare duplicati."
            }

        # B) Per combinazione cedente + numero documento + data documento
        cursor.execute("""
            SELECT id, filename, numero_documento 
            FROM documenti 
            WHERE cedente_piva = ? AND numero_documento = ? AND data_documento = ?
        """, (piva_cedente, num_doc, data_doc))
        dup_by_key = cursor.fetchone()
        if dup_by_key:
            return {
                "success": False,
                "is_duplicate": True,
                "documento_id": dup_by_key["id"],
                "numero_documento": dup_by_key["numero_documento"],
                "message": f"Fattura {num_doc} del {data_doc} da P.IVA {piva_cedente} già registrata (ID {dup_by_key['id']}). Duplicato evitato."
            }

        # 3. Carica sedi e regole attive per l'assegnazione automatica
        cursor.execute("SELECT * FROM sedi WHERE is_active = 1")
        venues = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM regole_assegnazione ORDER BY priorita ASC")
        rules = [dict(row) for row in cursor.fetchall()]

        # Valutazione assegnazione sede
        assignment_result = AssignmentEngine.evaluate_assignment(parsed, venues, rules)

        doc_sede_id = assignment_result["sede_id"]
        doc_stato = assignment_result["stato_assegnazione"]
        doc_metodo = assignment_result["metodo_assegnazione"]
        righe_con_sede = assignment_result["righe"]

        # 4. Carica mappature prodotti per associare le righe ai prodotti canonici
        cursor.execute("SELECT * FROM mappature_prodotto ORDER BY id ASC")
        mappings = [dict(row) for row in cursor.fetchall()]

        # Inserisci documento principale
        ddt_json = json.dumps(parsed.get("ddt_list", []), ensure_ascii=False)
        cursor.execute("""
            INSERT INTO documenti (
                filename, file_hash, sdi_identificativo, tipo_documento, numero_documento,
                data_documento, cedente_denominazione, cedente_piva, cedente_codice_fiscale,
                cedente_indirizzo, cedente_comune, cessionario_piva, cessionario_denominazione,
                importo_totale, imponibile_totale, iva_totale, divisa,
                sede_id, stato_assegnazione, metodo_assegnazione, ddt_elenco_json,
                indirizzo_resa_estratto, raw_xml
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            filename, file_hash, parsed["sdi_identificativo"], parsed["tipo_documento"],
            num_doc, data_doc, parsed["cedente_denominazione"], piva_cedente,
            parsed["cedente_codice_fiscale"], parsed["cedente_indirizzo"], parsed["cedente_comune"],
            parsed["cessionario_piva"], parsed["cessionario_denominazione"],
            parsed["importo_totale"], parsed["imponibile_totale"], parsed["iva_totale"],
            parsed["divisa"], doc_sede_id, doc_stato, doc_metodo, ddt_json,
            parsed["indirizzo_resa_estratto"], parsed["raw_xml"]
        ))
        documento_id = cursor.lastrowid

        # Inserisci ogni riga originale conservando traccia esatta
        righe_salvate = 0
        righe_mappate = 0
        for riga in righe_con_sede:
            # Match prodotto canonico
            matched_map = AssignmentEngine.match_product_mapping(
                riga["descrizione"], riga.get("codice_articolo", ""), piva_cedente, mappings
            )
            prodotto_id = matched_map["prodotto_id"] if matched_map else None
            if prodotto_id:
                righe_mappate += 1

            # Determina sede riga (ereditata dal documento o dalla riga)
            riga_sede_id = riga.get("sede_id") or doc_sede_id
            riga_metodo = riga.get("metodo_assegnazione") or (doc_metodo if doc_sede_id else "DA_ASSEGNARE")

            cursor.execute("""
                INSERT INTO righe_fattura (
                    documento_id, numero_linea, codice_articolo, descrizione,
                    quantita, unita_misura, prezzo_unitario_lordo, sconto_percentuale,
                    sconto_importo, prezzo_unitario_netto, prezzo_totale_netto, aliquota_iva,
                    riferimento_ddt_numero, riferimento_ddt_data, sede_id, metodo_assegnazione,
                    prodotto_id, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                documento_id, riga["numero_linea"], riga.get("codice_articolo", ""),
                riga["descrizione"], riga["quantita"], riga.get("unita_misura", "PZ"),
                riga["prezzo_unitario_lordo"], riga.get("sconto_percentuale", 0.0),
                riga.get("sconto_importo", 0.0), riga["prezzo_unitario_netto"],
                riga["prezzo_totale_netto"], riga.get("aliquota_iva", 0.0),
                riga.get("riferimento_ddt_numero", ""), riga.get("riferimento_ddt_data", ""),
                riga_sede_id, riga_metodo, prodotto_id, None
            ))
            righe_salvate += 1

        conn.commit()

        # Determina etichetta sede per risposta
        nome_sede = "Non Assegnata (In attesa)"
        if doc_sede_id:
            for v in venues:
                if v["id"] == doc_sede_id:
                    nome_sede = v["nome"]
                    break
        elif doc_stato == "PARZIALE" or doc_metodo == "AUTO_DDT":
            nome_sede = "Mista (Krügel & Cafè L'Incontro per DDT)"

        return {
            "success": True,
            "is_duplicate": False,
            "documento_id": documento_id,
            "numero_documento": num_doc,
            "data_documento": data_doc,
            "fornitore": parsed["cedente_denominazione"],
            "importo_totale": parsed["importo_totale"],
            "tipo_documento": parsed["tipo_documento"],
            "stato_assegnazione": doc_stato,
            "sede_assegnata": nome_sede,
            "metodo_assegnazione": doc_metodo,
            "spiegazione": assignment_result.get("spiegazione", ""),
            "righe_salvate": righe_salvate,
            "righe_mappate": righe_mappate,
            "message": f"Fattura {num_doc} importata con successo ({righe_salvate} righe)."
        }
