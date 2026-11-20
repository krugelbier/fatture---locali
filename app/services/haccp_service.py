# HACCP Business Logic Service
import calendar
import sqlite3
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple, Union

class HaccpService:
    @staticmethod
    def calculate_expiry(prep_dt_str: str, duration_hours: int = 48) -> str:
        """
        Calcola la data e ora di scadenza aggiungendo esattamente la durata in ore effettive
        alla data e ora di preparazione (es. 48 ore effettive anche al cambio dell'ora).
        """
        prep_dt_str = prep_dt_str.replace("T", " ")
        if len(prep_dt_str) == 16:
            dt_prep = datetime.strptime(prep_dt_str, "%Y-%m-%d %H:%M")
        elif len(prep_dt_str) == 19:
            dt_prep = datetime.strptime(prep_dt_str, "%Y-%m-%d %H:%M:%S")
        else:
            dt_prep = datetime.fromisoformat(prep_dt_str)

        dt_exp = dt_prep + timedelta(hours=duration_hours)
        return dt_exp.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def add_calendar_month(d: Union[datetime, date]) -> Union[datetime, date]:
        """
        Aggiunge un mese di calendario esatto secondo la regola HACCP:
        stesso giorno del mese successivo, oppure l'ultimo giorno disponibile
        se quel giorno non esiste nel mese di destinazione (es. 31 gennaio -> 28/29 febbraio, 31 marzo -> 30 aprile).
        """
        is_datetime = isinstance(d, datetime)
        year = d.year
        month = d.month + 1
        if month > 12:
            month = 1
            year += 1

        _, max_days = calendar.monthrange(year, month)
        target_day = min(d.day, max_days)

        if is_datetime:
            return d.replace(year=year, month=month, day=target_day)
        else:
            return date(year, month, target_day)

    @staticmethod
    def get_cleaning_deadline(tipo_pulizia: str, exec_date: date) -> date:
        """
        Calcola la scadenza per la tipologia di pulizia:
        - muri: 1 mese di calendario
        - vetri: 1 mese di calendario
        - magazzino: 7 giorni
        """
        if tipo_pulizia in ("muri", "vetri"):
            return HaccpService.add_calendar_month(exec_date)
        else:
            # magazzino
            return exec_date + timedelta(days=7)

    @staticmethod
    def get_pest_deadline(exec_date: date) -> date:
        """Monitoraggio infestanti: 1 mese di calendario"""
        return HaccpService.add_calendar_month(exec_date)

    @staticmethod
    def generate_next_lotto_interno(conn: sqlite3.Connection, sede_id: int) -> str:
        """
        Genera in modo atomico, thread-safe e concorrente il progressivo interno univoco del lotto
        per il locale specificato (LAV-000001 per Lavis, PER-000001 per Pergine).
        """
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE haccp_lotti_contatore
            SET ultimo_progressivo = ultimo_progressivo + 1
            WHERE sede_id = ?
        """, (sede_id,))
        
        cursor.execute("""
            SELECT ultimo_progressivo, prefisso
            FROM haccp_lotti_contatore
            WHERE sede_id = ?
        """, (sede_id,))
        row = cursor.fetchone()
        
        if not row:
            pref = "LAV" if sede_id == 1 else "PER"
            cursor.execute("""
                INSERT INTO haccp_lotti_contatore (sede_id, ultimo_progressivo, prefisso)
                VALUES (?, 1, ?)
            """, (sede_id, pref))
            prog = 1
        else:
            prog = row["ultimo_progressivo"]
            pref = row["prefisso"]
            
        return f"{pref}-{prog:06d}"

    @staticmethod
    def format_time_elapsed(delta: timedelta) -> str:
        """Formatta il tempo trascorso / scaduto in italiano chiaro e leggibile"""
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            total_seconds = abs(total_seconds)

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        if days > 30:
            mesi = days // 30
            return f"{mesi} {'mese' if mesi == 1 else 'mesi'}"
        elif days > 0:
            if hours > 0 and days < 3:
                return f"{days} {'giorno' if days == 1 else 'giorni'} e {hours} {'ora' if hours == 1 else 'ore'}"
            return f"{days} {'giorno' if days == 1 else 'giorni'}"
        elif hours > 0:
            if minutes > 0 and hours < 4:
                return f"{hours} {'ora' if hours == 1 else 'ore'} e {minutes} min"
            return f"{hours} {'ora' if hours == 1 else 'ore'}"
        else:
            return f"{max(1, minutes)} minuti"

    @staticmethod
    def get_current_iso_week(target_date: Optional[date] = None) -> Tuple[int, int, str, str]:
        if not target_date:
            target_date = datetime.now().date()
        iso_year, iso_week, _ = target_date.isocalendar()
        monday = target_date - timedelta(days=target_date.weekday())
        sunday = monday + timedelta(days=6)
        return iso_year, iso_week, monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

    @staticmethod
    def format_iso_week_label(year: int, week: int, monday_str: str, sunday_str: str) -> str:
        m_dt = datetime.strptime(monday_str, "%Y-%m-%d")
        s_dt = datetime.strptime(sunday_str, "%Y-%m-%d")
        return f"Settimana {week} ({m_dt.strftime('%d/%m')} - {s_dt.strftime('%d/%m/%Y')})"
