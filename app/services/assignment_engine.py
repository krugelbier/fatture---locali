# Assignment Engine for Fatture Locali (Krügel & Cafè L'Incontro)
import re
from typing import Dict, Any, List, Optional, Tuple

class AssignmentEngine:
    @staticmethod
    def _match_text_against_venue(text: str, venue: Dict[str, Any], rules: List[Dict[str, Any]] = None) -> bool:
        if not text:
            return False
        
        t_clean = text.lower()

        # Verifica codice sede (es. KRUGEL o INCONTRO)
        codice = (venue.get("codice") or "").strip().lower()
        if codice and len(codice) >= 3 and codice in t_clean:
            return True

        # Verifica nome sede
        nome = (venue.get("nome") or "").strip().lower()
        if nome:
            # Rimuovi accenti comuni per robustezza
            norm_nome = nome.replace("’", "'").replace("è", "e").replace("ü", "u")
            norm_text = t_clean.replace("’", "'").replace("è", "e").replace("ü", "u")
            if norm_nome in norm_text:
                return True

        # Verifica indirizzo sede
        ind = (venue.get("indirizzo") or "").strip().lower()
        if ind and len(ind) >= 5 and ind in t_clean:
            return True

        # Verifica parole chiave
        keywords_str = venue.get("parole_chiave") or ""
        keywords = [k.strip().lower() for k in keywords_str.split(",") if k.strip()]
        for kw in keywords:
            if kw and kw in t_clean:
                return True

        # Verifica regole custom configurate dall'utente
        if rules:
            for rule in rules:
                if rule.get("sede_id") == venue["id"]:
                    val = (rule.get("valore_match") or "").strip().lower()
                    op = rule.get("operatore", "CONTIENE")
                    if op == "CONTIENE" and val in t_clean:
                        return True
                    elif op == "UGUALE" and val == t_clean:
                        return True
                    elif op == "INIZIA_CON" and t_clean.startswith(val):
                        return True
                    elif op == "REGEX":
                        try:
                            if re.search(val, t_clean, re.IGNORECASE):
                                return True
                        except re.error:
                            pass

        return False

    @classmethod
    def evaluate_assignment(cls, doc_data: Dict[str, Any], venues: List[Dict[str, Any]], rules: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analizza una fattura e determina:
        1. Se univocamente associabile a una sede (Krügel o Cafè L'Incontro) per indirizzo/codice.
        2. Se mista con DDT diversi per riga assegnabili con certezza.
        3. Altrimenti lascia da assegnare.
        """
        # Mappa sedi per ID
        venue_by_id = {v["id"]: v for v in venues}
        
        # 1. Raccogliamo tutti i riferimenti di testo a livello di documento
        doc_texts = []
        if doc_data.get("indirizzo_resa_estratto"):
            doc_texts.append(doc_data["indirizzo_resa_estratto"])

        # 2. Controlliamo se ci sono DDT con assegnazioni per-linea
        ddt_list = doc_data.get("ddt_list", [])
        line_ddt_venues = {} # line_number -> venue_id
        ddt_matched_venues = set()

        for ddt in ddt_list:
            ddt_text = f"{ddt.get('numero_ddt', '')} {ddt.get('data_ddt', '')} {ddt.get('indirizzo_resa', '')}"
            matched_for_ddt = []
            for v in venues:
                if cls._match_text_against_venue(ddt_text, v, rules):
                    matched_for_ddt.append(v["id"])
            
            # Se questo specifico DDT punta univocamente a una sola sede
            if len(matched_for_ddt) == 1:
                target_v_id = matched_for_ddt[0]
                ddt_matched_venues.add(target_v_id)
                for line_idx in ddt.get("riferimento_linee", []):
                    line_ddt_venues[line_idx] = target_v_id

        # 3. Caso MISTO: se DDT multipli puntano a sedi diverse con certezza di linea
        if len(ddt_matched_venues) > 1 and line_ddt_venues:
            # Abbiamo consegne a entrambe le sedi con riferimenti ai DDT!
            # Assegniamo le singole righe collegate
            righe_aggiornate = []
            righe_assegnate_count = 0
            for r in doc_data.get("righe", []):
                l_num = r.get("numero_linea")
                v_id = line_ddt_venues.get(l_num)
                if v_id:
                    r["sede_id"] = v_id
                    r["metodo_assegnazione"] = "AUTO_DDT"
                    righe_assegnate_count += 1
                else:
                    r["sede_id"] = None
                    r["metodo_assegnazione"] = "DA_ASSEGNARE"
                righe_aggiornate.append(r)

            all_lines_count = len(righe_aggiornate)
            stato = "COMPLETA" if righe_assegnate_count == all_lines_count else "PARZIALE"

            return {
                "sede_id": None, # Mista: nessuna singola sede per l'intero documento
                "stato_assegnazione": stato,
                "metodo_assegnazione": "AUTO_DDT",
                "righe": righe_aggiornate,
                "spiegazione": f"Fattura mista con DDT separati: {righe_assegnate_count} su {all_lines_count} righe assegnate automaticamente alle sedi corrispondenti."
            }

        # 4. Caso Documento Univoco: cerchiamo corrispondenza con l'indirizzo resa generale o l'unico DDT
        full_doc_text = " ".join(doc_texts)
        if not full_doc_text and ddt_list:
            full_doc_text = " ".join([d.get("indirizzo_resa", "") for d in ddt_list])

        matching_venues = []
        for v in venues:
            if cls._match_text_against_venue(full_doc_text, v, rules):
                matching_venues.append(v)

        # Se c'è una corrispondenza univoca per l'intero documento
        if len(matching_venues) == 1:
            matched_v = matching_venues[0]
            v_id = matched_v["id"]
            righe_aggiornate = []
            for r in doc_data.get("righe", []):
                r["sede_id"] = v_id
                r["metodo_assegnazione"] = "AUTO_INDIRIZZO"
                righe_aggiornate.append(r)

            return {
                "sede_id": v_id,
                "stato_assegnazione": "COMPLETA",
                "metodo_assegnazione": "AUTO_INDIRIZZO",
                "righe": righe_aggiornate,
                "spiegazione": f"Corrispondenza univoca con indirizzo/codice di {matched_v['nome']}."
            }

        # 5. Se non univoco o nessun match trovato: DA_ASSEGNARE manualmente
        righe_aggiornate = []
        for r in doc_data.get("righe", []):
            r["sede_id"] = None
            r["metodo_assegnazione"] = "DA_ASSEGNARE"
            righe_aggiornate.append(r)

        spiegazione = "Nessun indirizzo di consegna o codice sede riconosciuto univocamente."
        if len(matching_venues) > 1:
            spiegazione = "Trovata corrispondenza ambigua per più sedi senza dettaglio DDT per riga."

        return {
            "sede_id": None,
            "stato_assegnazione": "DA_ASSEGNARE",
            "metodo_assegnazione": "DA_ASSEGNARE",
            "righe": righe_aggiornate,
            "spiegazione": spiegazione
        }

    @classmethod
    def match_product_mapping(cls, desc_line: str, cod_line: str, supplier_piva: str, mappings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Associa automaticamente una riga di fattura al prodotto canonico
        cercando nelle mappature configurate con il rispettivo fattore di conversione.
        """
        t_desc = (desc_line or "").upper()
        t_cod = (cod_line or "").upper()

        for m in mappings:
            # Se la mappatura è specifica per fornitore, controlla la P.IVA
            m_piva = m.get("fornitore_piva")
            if m_piva and m_piva.strip() and m_piva.strip() != supplier_piva.strip():
                continue

            pat = (m.get("pattern_testo") or "").upper().strip()
            if not pat:
                continue

            m_type = m.get("tipo_match", "CONTIENE")
            matched = False

            if m_type == "CONTIENE":
                if pat in t_desc or (t_cod and pat in t_cod):
                    matched = True
            elif m_type == "UGUALE":
                if pat == t_desc or pat == t_cod:
                    matched = True
            elif m_type == "REGEX":
                try:
                    if re.search(pat, t_desc, re.IGNORECASE) or (t_cod and re.search(pat, t_cod, re.IGNORECASE)):
                        matched = True
                except re.error:
                    pass

            if matched:
                return m

        return None
