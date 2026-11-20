# Analytics Service for Fatture Locali
# Calculates 6-month purchase statistics, weighted average prices, min/max, 
# pack conversions, and line-level traceability.
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import sqlite3

class AnalyticsService:
    @staticmethod
    def get_purchase_analytics(
        conn: sqlite3.Connection,
        months_back: int = 6,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sede_id: Optional[int] = None,
        prodotto_id: Optional[int] = None,
        categoria: Optional[str] = None,
        fornitore: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Calcola l'analisi acquisti aggregata per prodotto e fornitore negli ultimi 6 mesi.
        Include quantità fatturata, prezzo medio ponderato, min e max netti,
        e gestisce le conversioni delle confezioni e le note di credito.
        """
        cursor = conn.cursor()

        # Determina range temporale
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        if not date_from:
            # Calcola 6 mesi fa
            six_months_ago = datetime.now() - timedelta(days=months_back * 30)
            date_from = six_months_ago.strftime("%Y-%m-%d")

        # Query di base su tutte le righe di fattura nel periodo
        # Consideriamo sia le fatture assegnate a livello documento sia a livello riga
        query = """
        SELECT 
            r.id as riga_id,
            r.numero_linea,
            r.codice_articolo,
            r.descrizione as riga_descrizione,
            r.quantita as riga_quantita,
            r.unita_misura as riga_um,
            r.prezzo_unitario_lordo,
            r.sconto_percentuale,
            r.sconto_importo,
            r.prezzo_unitario_netto,
            r.prezzo_totale_netto,
            r.riferimento_ddt_numero,
            r.riferimento_ddt_data,
            COALESCE(r.sede_id, d.sede_id) as sede_effettiva_id,
            s.nome as sede_nome,
            s.colore_badge as sede_colore,
            d.id as documento_id,
            d.numero_documento,
            d.data_documento,
            d.tipo_documento,
            d.cedente_denominazione,
            d.cedente_piva,
            p.id as prodotto_id,
            p.nome_canonico as prodotto_nome,
            p.categoria as prodotto_categoria,
            p.unita_base as prodotto_um_base,
            m.fattore_conversione,
            m.unita_confezione
        FROM righe_fattura r
        JOIN documenti d ON r.documento_id = d.id
        LEFT JOIN sedi s ON COALESCE(r.sede_id, d.sede_id) = s.id
        LEFT JOIN prodotti p ON r.prodotto_id = p.id
        LEFT JOIN mappature_prodotto m ON (
            m.prodotto_id = p.id 
            AND (
                m.fornitore_piva IS NULL 
                OR m.fornitore_piva = '' 
                OR m.fornitore_piva = d.cedente_piva
            )
            AND (
                UPPER(r.descrizione) LIKE '%' || UPPER(m.pattern_testo) || '%' 
                OR UPPER(COALESCE(r.codice_articolo, '')) LIKE '%' || UPPER(m.pattern_testo) || '%'
            )
        )
        WHERE d.data_documento >= ? AND d.data_documento <= ?
        """

        params = [date_from, date_to]

        if sede_id:
            query += " AND COALESCE(r.sede_id, d.sede_id) = ?"
            params.append(sede_id)

        if prodotto_id:
            query += " AND p.id = ?"
            params.append(prodotto_id)

        if categoria:
            query += " AND p.categoria = ?"
            params.append(categoria)

        if fornitore:
            query += " AND UPPER(d.cedente_denominazione) LIKE ?"
            params.append(f"%{fornitore.upper()}%")

        query += " ORDER BY p.nome_canonico ASC, d.cedente_denominazione ASC, d.data_documento DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Raggruppamento in memoria per (prodotto_id, fornitore) o per prodotto se non mappato
        groups = {}

        for row in rows:
            p_id = row["prodotto_id"]
            if not p_id:
                # Prodotto non ancora mappato: lo raggruppiamo temporaneamente per descrizione originale
                group_key = (f"UNMAPPED_{row['riga_descrizione']}", row["cedente_denominazione"])
                prod_name = f"[Da Mappare] {row['riga_descrizione']}"
                cat = "Non Assegnato"
                um_base = row["riga_um"] or "PZ"
                is_mapped = False
            else:
                group_key = (p_id, row["cedente_denominazione"])
                prod_name = row["prodotto_nome"]
                cat = row["prodotto_categoria"]
                um_base = row["prodotto_um_base"]
                is_mapped = True

            factor = row["fattore_conversione"] or 1.0
            if factor <= 0:
                factor = 1.0

            # Quantità normalizzata nell'unità base del prodotto
            raw_qty = row["riga_quantita"]
            raw_total_net = row["prezzo_totale_netto"]
            is_credit_note = row["tipo_documento"] in ["TD04", "TD08"]

            # Per nota di credito: storna quantità e importo
            sign = -1.0 if is_credit_note else 1.0
            norm_qty = (raw_qty * factor) * sign
            effective_total_net = raw_total_net * sign

            # Prezzo unitario normalizzato per unità base
            # Esempio: se 1 fusto da 30L costa 90€, prezzo/L = 90 / 30 = 3.00€
            # Se la riga ha sconto, prezzo_totale_netto / norm_qty
            if raw_qty * factor != 0:
                norm_unit_price = round(raw_total_net / (raw_qty * factor), 4)
            else:
                norm_unit_price = round(row["prezzo_unitario_netto"] / factor, 4)

            if group_key not in groups:
                groups[group_key] = {
                    "prodotto_id": p_id,
                    "is_mapped": is_mapped,
                    "prodotto_nome": prod_name,
                    "categoria": cat,
                    "unita_base": um_base,
                    "fornitore": row["cedente_denominazione"],
                    "fornitore_piva": row["cedente_piva"],
                    "somma_quantita_base": 0.0,
                    "somma_importo_netto": 0.0,
                    "prezzi_unitari_base": [],
                    "sedi_coinvolte": set(),
                    "num_fatture": set(),
                    "num_righe": 0,
                    "ultima_data": row["data_documento"],
                    "ultimo_prezzo_netto": norm_unit_price,
                    "fattore_usato": factor,
                    "confezione_desc": row["unita_confezione"] or f"1x ({um_base})"
                }

            grp = groups[group_key]
            grp["somma_quantita_base"] += norm_qty
            grp["somma_importo_netto"] += effective_total_net
            
            # Per min/max consideriamo solo acquisti effettivi (non note di credito di storno)
            if not is_credit_note and norm_unit_price > 0:
                grp["prezzi_unitari_base"].append(norm_unit_price)

            if row["sede_nome"]:
                grp["sedi_coinvolte"].add(row["sede_nome"])
            else:
                grp["sedi_coinvolte"].add("Non assegnata")

            grp["num_fatture"].add(row["documento_id"])
            grp["num_righe"] += 1
            if row["data_documento"] > grp["ultima_data"]:
                grp["ultima_data"] = row["data_documento"]
                grp["ultimo_prezzo_netto"] = norm_unit_price

        # Costruzione del risultato finale
        results = []
        for (p_key, fornitore_name), grp in groups.items():
            tot_qty = round(grp["somma_quantita_base"], 2)
            tot_net = round(grp["somma_importo_netto"], 2)

            # Prezzo medio ponderato = Somma(importo netto) / Somma(quantità base)
            if tot_qty > 0 and tot_net > 0:
                prezzo_medio_ponderato = round(tot_net / tot_qty, 4)
            elif grp["prezzi_unitari_base"]:
                prezzo_medio_ponderato = round(sum(grp["prezzi_unitari_base"]) / len(grp["prezzi_unitari_base"]), 4)
            else:
                prezzo_medio_ponderato = 0.0

            prezzo_min = round(min(grp["prezzi_unitari_base"]), 4) if grp["prezzi_unitari_base"] else prezzo_medio_ponderato
            prezzo_max = round(max(grp["prezzi_unitari_base"]), 4) if grp["prezzi_unitari_base"] else prezzo_medio_ponderato

            # Variazione % tra min e max
            delta_perc = 0.0
            if prezzo_min > 0:
                delta_perc = round(((prezzo_max - prezzo_min) / prezzo_min) * 100.0, 1)

            results.append({
                "prodotto_id": grp["prodotto_id"],
                "is_mapped": grp["is_mapped"],
                "prodotto_nome": grp["prodotto_nome"],
                "categoria": grp["categoria"],
                "unita_base": grp["unita_base"],
                "fornitore": grp["fornitore"],
                "fornitore_piva": grp["fornitore_piva"],
                "quantita_fatturata": tot_qty,
                "importo_totale_netto": tot_net,
                "prezzo_medio_ponderato": prezzo_medio_ponderato,
                "prezzo_min": prezzo_min,
                "prezzo_max": prezzo_max,
                "variazione_perc": delta_perc,
                "ultimo_prezzo_netto": grp["ultimo_prezzo_netto"],
                "ultima_data": grp["ultima_data"],
                "sedi": list(grp["sedi_coinvolte"]),
                "num_fatture": len(grp["num_fatture"]),
                "num_righe": grp["num_righe"],
                "confezione_desc": grp["confezione_desc"]
            })

        # Ordina per Nome Prodotto poi Fornitore
        results.sort(key=lambda x: (x["is_mapped"] is False, x["prodotto_nome"], x["fornitore"]))
        return results

    @staticmethod
    def get_price_drilldown_lines(
        conn: sqlite3.Connection,
        prodotto_id: Optional[int] = None,
        raw_description: Optional[str] = None,
        fornitore: Optional[str] = None,
        sede_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Restituisce il dettaglio riga per riga di tutte le fatture
        che compongono il prezzo di acquisto di un prodotto, con tracciabilità completa.
        """
        cursor = conn.cursor()

        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        if not date_from:
            date_from = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

        query = """
        SELECT 
            r.id as riga_id,
            r.numero_linea,
            r.codice_articolo,
            r.descrizione as descrizione_originale,
            r.quantita as quantita_originale,
            r.unita_misura as um_originale,
            r.prezzo_unitario_lordo,
            r.sconto_percentuale,
            r.sconto_importo,
            r.prezzo_unitario_netto,
            r.prezzo_totale_netto,
            r.aliquota_iva,
            r.riferimento_ddt_numero,
            r.riferimento_ddt_data,
            r.metodo_assegnazione as metodo_riga,
            COALESCE(r.sede_id, d.sede_id) as sede_effettiva_id,
            s.nome as sede_nome,
            s.colore_badge as sede_colore,
            d.id as documento_id,
            d.numero_documento,
            d.data_documento,
            d.tipo_documento,
            d.cedente_denominazione,
            d.cedente_piva,
            p.id as prodotto_id,
            p.nome_canonico as prodotto_nome,
            p.unita_base as prodotto_um_base,
            m.fattore_conversione,
            m.unita_confezione
        FROM righe_fattura r
        JOIN documenti d ON r.documento_id = d.id
        LEFT JOIN sedi s ON COALESCE(r.sede_id, d.sede_id) = s.id
        LEFT JOIN prodotti p ON r.prodotto_id = p.id
        LEFT JOIN mappature_prodotto m ON (
            m.prodotto_id = p.id 
            AND (m.fornitore_piva IS NULL OR m.fornitore_piva = '' OR m.fornitore_piva = d.cedente_piva)
            AND (UPPER(r.descrizione) LIKE '%' || UPPER(m.pattern_testo) || '%')
        )
        WHERE d.data_documento >= ? AND d.data_documento <= ?
        """

        params = [date_from, date_to]

        if prodotto_id:
            query += " AND r.prodotto_id = ?"
            params.append(prodotto_id)
        elif raw_description:
            query += " AND r.descrizione = ?"
            params.append(raw_description)

        if fornitore:
            query += " AND d.cedente_denominazione = ?"
            params.append(fornitore)

        if sede_id:
            query += " AND COALESCE(r.sede_id, d.sede_id) = ?"
            params.append(sede_id)

        query += " ORDER BY d.data_documento DESC, d.numero_documento DESC, r.numero_linea ASC"

        cursor.execute(query, params)
        lines = []
        for row in cursor.fetchall():
            factor = row["fattore_conversione"] or 1.0
            if factor <= 0:
                factor = 1.0

            is_credit_note = row["tipo_documento"] in ["TD04", "TD08"]
            sign = -1.0 if is_credit_note else 1.0
            qty_base = round(row["quantita_originale"] * factor * sign, 2)
            
            # Prezzo unitario normalizzato per unità base
            if row["quantita_originale"] * factor != 0:
                norm_unit_price = round(row["prezzo_totale_netto"] / (row["quantita_originale"] * factor), 4)
            else:
                norm_unit_price = round(row["prezzo_unitario_netto"] / factor, 4)

            lines.append({
                "riga_id": row["riga_id"],
                "documento_id": row["documento_id"],
                "numero_documento": row["numero_documento"],
                "data_documento": row["data_documento"],
                "tipo_documento": row["tipo_documento"],
                "is_credit_note": is_credit_note,
                "cedente_denominazione": row["cedente_denominazione"],
                "cedente_piva": row["cedente_piva"],
                "numero_linea": row["numero_linea"],
                "codice_articolo": row["codice_articolo"],
                "descrizione_originale": row["descrizione_originale"],
                "quantita_originale": row["quantita_originale"],
                "um_originale": row["um_originale"],
                "prezzo_unitario_lordo": row["prezzo_unitario_lordo"],
                "sconto_percentuale": row["sconto_percentuale"],
                "sconto_importo": row["sconto_importo"],
                "prezzo_unitario_netto": row["prezzo_unitario_netto"],
                "prezzo_totale_netto": round(row["prezzo_totale_netto"] * sign, 2),
                "aliquota_iva": row["aliquota_iva"],
                "riferimento_ddt_numero": row["riferimento_ddt_numero"],
                "riferimento_ddt_data": row["riferimento_ddt_data"],
                "sede_nome": row["sede_nome"] or "Non assegnata",
                "sede_colore": row["sede_colore"] or "#9ca3af",
                "metodo_assegnazione": row["metodo_riga"],
                "prodotto_nome": row["prodotto_nome"],
                "prodotto_um_base": row["prodotto_um_base"] or row["um_originale"],
                "fattore_conversione": factor,
                "confezione_desc": row["unita_confezione"] or "1x",
                "quantita_base": qty_base,
                "prezzo_unitario_base": norm_unit_price
            })

        return lines
