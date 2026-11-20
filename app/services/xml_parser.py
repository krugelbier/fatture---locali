# XML FatturaPA Parser and Validator for Italian Electronic Invoices
import xml.etree.ElementTree as ET
import hashlib
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

class FatturaPAParser:
    @staticmethod
    def extract_xml_from_bytes(file_bytes: bytes, filename: str) -> str:
        """Estrae l'XML anche se il file è firmato digitalmente in formato CAdES (.p7m)"""
        # Se è un file .p7m o contiene header binario, estraiamo il payload XML
        if filename.lower().endswith(".p7m") or b"<?xml" in file_bytes or b"<FatturaElettronica" in file_bytes or b"<p:FatturaElettronica" in file_bytes:
            start_idx = file_bytes.find(b"<?xml")
            if start_idx == -1:
                start_idx = file_bytes.find(b"<p:FatturaElettronica")
            if start_idx == -1:
                start_idx = file_bytes.find(b"<FatturaElettronica")
            
            if start_idx != -1:
                end_idx = file_bytes.rfind(b"</p:FatturaElettronica>")
                if end_idx != -1:
                    end_idx += len(b"</p:FatturaElettronica>")
                else:
                    end_idx = file_bytes.rfind(b"</FatturaElettronica>")
                    if end_idx != -1:
                        end_idx += len(b"</FatturaElettronica>")
                
                if end_idx != -1 and end_idx > start_idx:
                    xml_slice = file_bytes[start_idx:end_idx]
                    for enc in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                        try:
                            return xml_slice.decode(enc)
                        except UnicodeDecodeError:
                            continue

        # Tentativo standard di decodifica diretta
        for enc in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
            try:
                return file_bytes.decode(enc)
            except UnicodeDecodeError:
                continue

        raise ValueError(f"Impossibile decodificare il file {filename}: formato non riconosciuto.")

    @classmethod
    def parse_file(cls, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Esegue il parsing completo di una FatturaPA 1.2 o Nota di Credito"""
        xml_text = cls.extract_xml_from_bytes(file_bytes, filename)
        file_hash = hashlib.sha256(xml_text.encode('utf-8')).hexdigest()

        # Rimuovi eventuali dichiarazioni o strip namespace per facilitare il parsing
        root = ET.fromstring(xml_text)
        
        # Helper per cercare tag ignorando il namespace
        def find_text(elem, tag_name: str, default: str = "") -> str:
            if elem is None:
                return default
            for child in elem.iter():
                clean_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if clean_tag == tag_name and child.text:
                    return child.text.strip()
            return default

        def find_elem(elem, tag_name: str):
            if elem is None:
                return None
            for child in elem.iter():
                clean_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if clean_tag == tag_name:
                    return child
            return None

        def find_all_elems(elem, tag_name: str):
            if elem is None:
                return []
            res = []
            for child in elem.iter():
                clean_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if clean_tag == tag_name:
                    res.append(child)
            return res

        header = find_elem(root, "FatturaElettronicaHeader")
        body = find_elem(root, "FatturaElettronicaBody")
        if body is None:
            raise ValueError(f"Il file {filename} non contiene la sezione FatturaElettronicaBody.")

        # --- Dati Cedente / Fornitore ---
        cedente = find_elem(header, "CedentePrestatore")
        cedente_denominazione = ""
        cedente_piva = ""
        cedente_cf = ""
        cedente_indirizzo = ""
        cedente_comune = ""

        if cedente is not None:
            anagrafica = find_elem(cedente, "DatiAnagrafici")
            if anagrafica is not None:
                cedente_piva = find_text(find_elem(anagrafica, "IdFiscaleIVA"), "IdCodice")
                cedente_cf = find_text(anagrafica, "CodiceFiscale")
                den = find_text(find_elem(anagrafica, "Anagrafica"), "Denominazione")
                if not den:
                    nome = find_text(find_elem(anagrafica, "Anagrafica"), "Nome")
                    cognome = find_text(find_elem(anagrafica, "Anagrafica"), "Cognome")
                    den = f"{nome} {cognome}".strip()
                cedente_denominazione = den

            sede_cedente = find_elem(cedente, "Sede")
            if sede_cedente is not None:
                cedente_indirizzo = find_text(sede_cedente, "Indirizzo")
                cedente_comune = find_text(sede_cedente, "Comune")

        # --- Dati Cessionario / Committente (Krügel / Cafè L'Incontro) ---
        cessionario = find_elem(header, "CessionarioCommittente")
        cessionario_piva = ""
        cessionario_denominazione = ""
        if cessionario is not None:
            anag = find_elem(cessionario, "DatiAnagrafici")
            if anag is not None:
                cessionario_piva = find_text(find_elem(anag, "IdFiscaleIVA"), "IdCodice") or find_text(anag, "CodiceFiscale")
                den = find_text(find_elem(anag, "Anagrafica"), "Denominazione")
                if not den:
                    nome = find_text(find_elem(anag, "Anagrafica"), "Nome")
                    cognome = find_text(find_elem(anag, "Anagrafica"), "Cognome")
                    den = f"{nome} {cognome}".strip()
                cessionario_denominazione = den

        # --- Dati Generali Documento ---
        dati_generali = find_elem(body, "DatiGeneraliDocumento")
        tipo_documento = find_text(dati_generali, "TipoDocumento", "TD01")
        divisa = find_text(dati_generali, "Divisa", "EUR")
        data_documento = find_text(dati_generali, "Data", "")
        numero_documento = find_text(dati_generali, "Numero", "")
        importo_totale_str = find_text(dati_generali, "ImportoTotaleDocumento", "0")
        try:
            importo_totale = float(importo_totale_str.replace(',', '.'))
        except ValueError:
            importo_totale = 0.0

        # Riferimento Indirizzo Resa Generale (se presente in DatiTrasporto o DatiDDT)
        indirizzo_resa_estratto_list = []
        dati_trasporto = find_elem(body, "DatiTrasporto")
        if dati_trasporto is not None:
            ind_resa = find_elem(dati_trasporto, "DatiIndirizzoResa")
            if ind_resa is not None:
                via = find_text(ind_resa, "Indirizzo")
                cap = find_text(ind_resa, "CAP")
                comune = find_text(ind_resa, "Comune")
                prov = find_text(ind_resa, "Provincia")
                full_ind = f"{via} {cap} {comune} {prov}".strip()
                if full_ind:
                    indirizzo_resa_estratto_list.append(full_ind)

        # DDT collegati (DatiDDT)
        ddt_list = []
        dati_ddt_elems = find_all_elems(body, "DatiDDT")
        for ddt_el in dati_ddt_elems:
            num_ddt = find_text(ddt_el, "NumeroDDT")
            data_ddt = find_text(ddt_el, "DataDDT")
            # Linee a cui questo DDT si riferisce
            linee_rif = []
            for rif in find_all_elems(ddt_el, "RiferimentoNumeroLinea"):
                if rif.text:
                    try:
                        linee_rif.append(int(rif.text.strip()))
                    except ValueError:
                        pass
            
            # Indirizzo resa specifico del DDT (se presente)
            ind_resa_ddt = find_elem(ddt_el, "IndirizzoResa")
            indirizzo_ddt_str = ""
            if ind_resa_ddt is not None:
                via = find_text(ind_resa_ddt, "Indirizzo")
                cap = find_text(ind_resa_ddt, "CAP")
                comune = find_text(ind_resa_ddt, "Comune")
                indirizzo_ddt_str = f"{via} {cap} {comune}".strip()
                if indirizzo_ddt_str and indirizzo_ddt_str not in indirizzo_resa_estratto_list:
                    indirizzo_resa_estratto_list.append(indirizzo_ddt_str)

            ddt_list.append({
                "numero_ddt": num_ddt,
                "data_ddt": data_ddt,
                "riferimento_linee": linee_rif,
                "indirizzo_resa": indirizzo_ddt_str
            })

        # --- Dettaglio Linee / Beni e Servizi ---
        dati_beni = find_elem(body, "DatiBeniServizi")
        righe = []
        imponibile_calcolato = 0.0

        if dati_beni is not None:
            linee_elems = find_all_elems(dati_beni, "DettaglioLinee")
            for linea_el in linee_elems:
                num_linea_str = find_text(linea_el, "NumeroLinea", "1")
                try:
                    num_linea = int(num_linea_str)
                except ValueError:
                    num_linea = len(righe) + 1

                codice_art = ""
                cod_elem = find_elem(linea_el, "CodiceArticolo")
                if cod_elem is not None:
                    codice_art = find_text(cod_elem, "CodiceValore")

                descrizione = find_text(linea_el, "Descrizione", "")
                
                # Se è una riga descrittiva o causale senza prezzo
                prezzo_un_str = find_text(linea_el, "PrezzoUnitario", "0")
                try:
                    prezzo_unitario_lordo = float(prezzo_un_str.replace(',', '.'))
                except ValueError:
                    prezzo_unitario_lordo = 0.0

                quantita_str = find_text(linea_el, "Quantita", "1")
                try:
                    quantita = float(quantita_str.replace(',', '.'))
                except ValueError:
                    quantita = 1.0

                unita_misura = find_text(linea_el, "UnitaMisura", "").strip().upper()
                if not unita_misura:
                    unita_misura = "PZ"

                # Gestione Sconti e Maggiorazioni
                sconto_perc = 0.0
                sconto_imp = 0.0
                prezzo_unitario_netto = prezzo_unitario_lordo

                sconti_elems = find_all_elems(linea_el, "ScontoMaggiorazione")
                for sc_elem in sconti_elems:
                    tipo_sc = find_text(sc_elem, "Tipo", "SC").upper()
                    perc_str = find_text(sc_elem, "Percentuale", "0")
                    imp_str = find_text(sc_elem, "Importo", "0")

                    try:
                        p = float(perc_str.replace(',', '.'))
                    except ValueError:
                        p = 0.0

                    try:
                        imp = float(imp_str.replace(',', '.'))
                    except ValueError:
                        imp = 0.0

                    if tipo_sc == "SC":  # Sconto
                        if p > 0:
                            sconto_perc = p
                            prezzo_unitario_netto = round(prezzo_unitario_netto * (1.0 - (p / 100.0)), 4)
                        elif imp > 0:
                            sconto_imp = imp
                            if quantita > 0:
                                prezzo_unitario_netto = round(prezzo_unitario_netto - (imp / quantita), 4)
                            else:
                                prezzo_unitario_netto = round(prezzo_unitario_netto - imp, 4)
                    elif tipo_sc == "MG":  # Maggiorazione
                        if p > 0:
                            prezzo_unitario_netto = round(prezzo_unitario_netto * (1.0 + (p / 100.0)), 4)
                        elif imp > 0:
                            if quantita > 0:
                                prezzo_unitario_netto = round(prezzo_unitario_netto + (imp / quantita), 4)

                prezzo_totale_str = find_text(linea_el, "PrezzoTotale", "0")
                try:
                    prezzo_totale_netto = float(prezzo_totale_str.replace(',', '.'))
                except ValueError:
                    prezzo_totale_netto = round(quantita * prezzo_unitario_netto, 2)

                # Se non c'era sconto esplicito ma PrezzoTotale differisce da Quantita * PrezzoUnitario
                if abs(quantita * prezzo_unitario_lordo - prezzo_totale_netto) > 0.01 and quantita > 0 and sconto_perc == 0 and sconto_imp == 0:
                    prezzo_unitario_netto = round(prezzo_totale_netto / quantita, 4)

                aliquota_iva_str = find_text(linea_el, "AliquotaIVA", "0")
                try:
                    aliquota_iva = float(aliquota_iva_str.replace(',', '.'))
                except ValueError:
                    aliquota_iva = 0.0

                # Per le Note di Credito (TD04), assicuriamoci che le quantità e gli importi
                # siano registrati con il loro valore assoluto nella riga ma contrassegnati,
                # oppure se già negativi li normalizziamo.
                # In FatturaPA le righe di TD04 sono spesso positive con segno implicito nel TipoDocumento.
                is_credit_note = tipo_documento in ["TD04", "TD08"]

                # Cerca DDT associato specificamente a questa linea
                ddt_collegato_num = ""
                ddt_collegato_data = ""
                for ddt in ddt_list:
                    if num_linea in ddt["riferimento_linee"]:
                        ddt_collegato_num = ddt["numero_ddt"]
                        ddt_collegato_data = ddt["data_ddt"]
                        break
                # Se c'è solo un DDT nella fattura e nessuna riga specificata, assegna quel DDT
                if not ddt_collegato_num and len(ddt_list) == 1:
                    ddt_collegato_num = ddt_list[0]["numero_ddt"]
                    ddt_collegato_data = ddt_list[0]["data_ddt"]

                righe.append({
                    "numero_linea": num_linea,
                    "codice_articolo": codice_art,
                    "descrizione": descrizione,
                    "quantita": quantita,
                    "unita_misura": unita_misura,
                    "prezzo_unitario_lordo": prezzo_unitario_lordo,
                    "sconto_percentuale": sconto_perc,
                    "sconto_importo": sconto_imp,
                    "prezzo_unitario_netto": prezzo_unitario_netto,
                    "prezzo_totale_netto": prezzo_totale_netto,
                    "aliquota_iva": aliquota_iva,
                    "riferimento_ddt_numero": ddt_collegato_num,
                    "riferimento_ddt_data": ddt_collegato_data,
                    "is_credit_note": is_credit_note
                })
                imponibile_calcolato += prezzo_totale_netto

        if importo_totale == 0.0 and imponibile_calcolato > 0:
            importo_totale = round(imponibile_calcolato * 1.22, 2)

        return {
            "filename": filename,
            "file_hash": file_hash,
            "sdi_identificativo": find_text(find_elem(header, "DatiTrasmissione"), "ProgressivoInvio", ""),
            "tipo_documento": tipo_documento,
            "numero_documento": numero_documento,
            "data_documento": data_documento,
            "cedente_denominazione": cedente_denominazione or "Fornitore non specificato",
            "cedente_piva": cedente_piva,
            "cedente_codice_fiscale": cedente_cf,
            "cedente_indirizzo": cedente_indirizzo,
            "cedente_comune": cedente_comune,
            "cessionario_piva": cessionario_piva,
            "cessionario_denominazione": cessionario_denominazione or "Krügel / Cafè L’Incontro",
            "importo_totale": importo_totale,
            "imponibile_totale": round(imponibile_calcolato, 2),
            "iva_totale": round(importo_totale - imponibile_calcolato, 2),
            "divisa": divisa,
            "ddt_list": ddt_list,
            "indirizzo_resa_estratto": " | ".join(indirizzo_resa_estratto_list),
            "righe": righe,
            "raw_xml": xml_text
        }
