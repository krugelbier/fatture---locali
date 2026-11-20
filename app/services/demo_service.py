# Realistic FatturaPA XML Generator and Demo Data Loader for Krügel & Cafè L'Incontro
import os
import sqlite3
from datetime import datetime, timedelta
from app.services.importer.xml_importer import XmlFileImporter

DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "demo_fatture")

def generate_demo_xmls():
    os.makedirs(DEMO_DIR, exist_ok=True)
    today = datetime.now()
    d_curr = today.strftime("%Y-%m-%d")
    d_1m = (today - timedelta(days=28)).strftime("%Y-%m-%d")
    d_2m = (today - timedelta(days=65)).strftime("%Y-%m-%d")
    d_3m = (today - timedelta(days=95)).strftime("%Y-%m-%d")
    d_4m = (today - timedelta(days=130)).strftime("%Y-%m-%d")

    xml_files = {
        # 1. Fattura Partesa per Krügel (Birre in fusto con sconto riga)
        "Fattura_01_Partesa_Krugel_Birre.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>05012340158</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>PAR2026-004521</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>SUBM70N</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>05012340158</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>05012340158</CodiceFiscale>
        <Anagrafica>
          <Denominazione>PARTESA S.P.A.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Edison 15</Indirizzo>
        <CAP>20090</CAP>
        <Comune>Assago</Comune>
        <Provincia>MI</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>02562290227</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>02562290227</CodiceFiscale>
        <Anagrafica>
          <Denominazione>GESTIONI LOCALI S.R.L. - KRUGEL &amp; CAFE L'INCONTRO</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Tamarisi 2</Indirizzo>
        <CAP>38015</CAP>
        <Comune>Lavis</Comune>
        <Provincia>TV</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{d_1m}</Data>
        <Numero>FT-2026/0942</Numero>
        <ImportoTotaleDocumento>932.78</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
      <DatiDDT>
        <NumeroDDT>DDT-84920</NumeroDDT>
        <DataDDT>{d_1m}</DataDDT>
        <RiferimentoNumeroLinea>1</RiferimentoNumeroLinea>
        <RiferimentoNumeroLinea>2</RiferimentoNumeroLinea>
        <RiferimentoNumeroLinea>3</RiferimentoNumeroLinea>
        <IndirizzoResa>
          <Indirizzo>Via Nazionale</Indirizzo>
          <CAP>38015</CAP>
          <Comune>Lavis</Comune>
          <Provincia>TV</Provincia>
          <Nazione>IT</Nazione>
        </IndirizzoResa>
      </DatiDDT>
      <DatiTrasporto>
        <DatiIndirizzoResa>
          <Indirizzo>Via Nazionale</Indirizzo>
          <CAP>38015</CAP>
          <Comune>Lavis</Comune>
          <Provincia>TV</Provincia>
        </DatiIndirizzoResa>
      </DatiTrasporto>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>BIR-HEIN-30L</CodiceValore>
        </CodiceArticolo>
        <Descrizione>HEINEKEN BIRRA FUSTO 30LT</Descrizione>
        <Quantita>4.00</Quantita>
        <UnitaMisura>FUSTO</UnitaMisura>
        <PrezzoUnitario>98.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>10.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>352.80</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>BIR-ICHN-30L</CodiceValore>
        </CodiceArticolo>
        <Descrizione>ICHNUSA NON FILTRATA FUSTO 30L</Descrizione>
        <Quantita>2.00</Quantita>
        <UnitaMisura>FUSTO</UnitaMisura>
        <PrezzoUnitario>105.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>8.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>193.20</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>3</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>BIR-PAUL-30L</CodiceValore>
        </CodiceArticolo>
        <Descrizione>PAULANER SALVATOR FUSTO 30L</Descrizione>
        <Quantita>2.00</Quantita>
        <UnitaMisura>FUSTO</UnitaMisura>
        <PrezzoUnitario>115.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>5.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>218.50</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""",

        # 2. Fattura Hausbrandt per Cafè L'Incontro (Caffè e fornitura bar)
        "Fattura_02_Hausbrandt_Incontro_Caffe.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>00198760263</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>HAU-2026-1029</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>SUBM70N</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>00198760263</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>00198760263</CodiceFiscale>
        <Anagrafica>
          <Denominazione>HAUSBRANDT TRIESTE 1892 S.P.A.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Foscarini 2</Indirizzo>
        <CAP>31040</CAP>
        <Comune>Nervesa della Battaglia</Comune>
        <Provincia>TV</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>02562290227</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>02562290227</CodiceFiscale>
        <Anagrafica>
          <Denominazione>GESTIONI LOCALI S.R.L. - CAFE L'INCONTRO</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Tamarisi 2</Indirizzo>
        <CAP>38015</CAP>
        <Comune>Lavis</Comune>
        <Provincia>TV</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{d_2m}</Data>
        <Numero>FT-HB-2026/410</Numero>
        <ImportoTotaleDocumento>514.35</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
      <DatiTrasporto>
        <DatiIndirizzoResa>
          <Indirizzo>Via Tamarisi 2</Indirizzo>
          <CAP>38015</CAP>
          <Comune>Lavis</Comune>
          <Provincia>TV</Provincia>
        </DatiIndirizzoResa>
      </DatiTrasporto>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>CAF-HB-GOURMET</CodiceValore>
        </CodiceArticolo>
        <Descrizione>HAUSBRANDT GOURMET CT 6X1KG MISCELA ESPRESSO</Descrizione>
        <Quantita>3.00</Quantita>
        <UnitaMisura>CT</UnitaMisura>
        <PrezzoUnitario>132.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>15.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>336.60</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>TE-ASS-100</CodiceValore>
        </CodiceArticolo>
        <Descrizione>TE E INFUSI ASSORTITI IN FILTRO CASSA 100 PZ</Descrizione>
        <Quantita>2.00</Quantita>
        <UnitaMisura>PZ</UnitaMisura>
        <PrezzoUnitario>24.50</PrezzoUnitario>
        <PrezzoTotale>49.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>3</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>ZUCCH-5KG</CodiceValore>
        </CodiceArticolo>
        <Descrizione>ZUCCHERO BIANCO IN BUSTINE CARTONE 5KG</Descrizione>
        <Quantita>2.00</Quantita>
        <UnitaMisura>CT</UnitaMisura>
        <PrezzoUnitario>18.00</PrezzoUnitario>
        <PrezzoTotale>36.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""",

        # 3. Fattura MISTA con DDT multipli assegnabili per riga!
        # DDT 1043 a Krügel (righe 1 e 2: Gin Mare & Zacapa)
        # DDT 1044 a Cafè L'Incontro (righe 3 e 4: Prosecco & Aperol)
        "Fattura_03_Beverage_Mista_Entrambe_Sedi.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>03216540268</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>VBD2026-8871</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>SUBM70N</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>03216540268</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>03216540268</CodiceFiscale>
        <Anagrafica>
          <Denominazione>VENETO BEVERAGE DISTRIBUTION S.R.L.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Postumia 44</Indirizzo>
        <CAP>31050</CAP>
        <Comune>Ponzano Veneto</Comune>
        <Provincia>TV</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>02562290227</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>02562290227</CodiceFiscale>
        <Anagrafica>
          <Denominazione>GESTIONI LOCALI S.R.L.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Tamarisi 2</Indirizzo>
        <CAP>38015</CAP>
        <Comune>Lavis</Comune>
        <Provincia>TV</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD24</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{d_curr}</Data>
        <Numero>FT-DIFF-2026/184</Numero>
        <ImportoTotaleDocumento>1205.85</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
      <!-- DDT 1 per Krügel -->
      <DatiDDT>
        <NumeroDDT>DDT-1043</NumeroDDT>
        <DataDDT>{d_curr}</DataDDT>
        <RiferimentoNumeroLinea>1</RiferimentoNumeroLinea>
        <RiferimentoNumeroLinea>2</RiferimentoNumeroLinea>
        <IndirizzoResa>
          <Indirizzo>Via Nazionale (Krügel Birreria)</Indirizzo>
          <CAP>38015</CAP>
          <Comune>Lavis</Comune>
          <Provincia>TV</Provincia>
        </IndirizzoResa>
      </DatiDDT>
      <!-- DDT 2 per Cafè L'Incontro -->
      <DatiDDT>
        <NumeroDDT>DDT-1044</NumeroDDT>
        <DataDDT>{d_curr}</DataDDT>
        <RiferimentoNumeroLinea>3</RiferimentoNumeroLinea>
        <RiferimentoNumeroLinea>4</RiferimentoNumeroLinea>
        <IndirizzoResa>
          <Indirizzo>Via Tamarisi 2 (Cafè L'Incontro)</Indirizzo>
          <CAP>38015</CAP>
          <Comune>Lavis</Comune>
          <Provincia>TV</Provincia>
        </IndirizzoResa>
      </DatiDDT>
    </DatiGenerali>
    <DatiBeniServizi>
      <!-- Linee Krügel -->
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>EAN</CodiceTipo>
          <CodiceValore>8437009405011</CodiceValore>
        </CodiceArticolo>
        <Descrizione>GIN MARE 70CL BOTTIGLIA</Descrizione>
        <Quantita>6.00</Quantita>
        <UnitaMisura>BT</UnitaMisura>
        <PrezzoUnitario>34.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>5.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>193.80</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>EAN</CodiceTipo>
          <CodiceValore>7401005001235</CodiceValore>
        </CodiceArticolo>
        <Descrizione>RUM ZACAPA 23 70CL</Descrizione>
        <Quantita>3.00</Quantita>
        <UnitaMisura>BT</UnitaMisura>
        <PrezzoUnitario>52.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>7.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>145.08</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <!-- Linee Cafè L'Incontro -->
      <DettaglioLinee>
        <NumeroLinea>3</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>VIN-VALD-DOCG</CodiceValore>
        </CodiceArticolo>
        <Descrizione>PROSECCO VALDOBBIADENE SUPERIORE DOCG CT 6 BT</Descrizione>
        <Quantita>10.00</Quantita>
        <UnitaMisura>CT</UnitaMisura>
        <PrezzoUnitario>54.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>10.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>486.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>4</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>EAN</CodiceTipo>
          <CodiceValore>8002270014901</CodiceValore>
        </CodiceArticolo>
        <Descrizione>APEROL 1L BOTTIGLIA</Descrizione>
        <Quantita>12.00</Quantita>
        <UnitaMisura>BT</UnitaMisura>
        <PrezzoUnitario>14.50</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>6.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>163.56</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""",

        # 4. Fattura DAC Alimentari per Krügel (Cucina, Hamburger & Patatine)
        "Fattura_04_Dac_Food_Krugel.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>01287650174</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>DAC2026-33910</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>SUBM70N</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>01287650174</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>01287650174</CodiceFiscale>
        <Anagrafica>
          <Denominazione>DAC S.P.A. ALIMENTARI</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Marconi 1</Indirizzo>
        <CAP>25020</CAP>
        <Comune>Flero</Comune>
        <Provincia>BS</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>02562290227</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>02562290227</CodiceFiscale>
        <Anagrafica>
          <Denominazione>GESTIONI LOCALI S.R.L.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Nazionale</Indirizzo>
        <CAP>38015</CAP>
        <Comune>Lavis</Comune>
        <Provincia>TV</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{d_2m}</Data>
        <Numero>FT-DAC-2026/891</Numero>
        <ImportoTotaleDocumento>556.81</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
      <DatiTrasporto>
        <DatiIndirizzoResa>
          <Indirizzo>Via Nazionale (Krügel)</Indirizzo>
          <CAP>38015</CAP>
          <Comune>Lavis</Comune>
          <Provincia>TV</Provincia>
        </DatiIndirizzoResa>
      </DatiTrasporto>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>CAR-ANGUS-200</CodiceValore>
        </CodiceArticolo>
        <Descrizione>HAMBURGER ANGUS 200G CT 25 PZ SURGELATI</Descrizione>
        <Quantita>4.00</Quantita>
        <UnitaMisura>CT</UnitaMisura>
        <PrezzoUnitario>62.50</PrezzoUnitario>
        <PrezzoTotale>250.00</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>SURG-PAT-DIP</CodiceValore>
        </CodiceArticolo>
        <Descrizione>PATATE DIPPER CT 10KG (4X2.5KG)</Descrizione>
        <Quantita>5.00</Quantita>
        <UnitaMisura>CT</UnitaMisura>
        <PrezzoUnitario>24.00</PrezzoUnitario>
        <PrezzoTotale>120.00</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>3</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>PAN-BUN-BRIOCHE</CodiceValore>
        </CodiceArticolo>
        <Descrizione>PANE HAMBURGER BRIOCHE BUN CT 48PZ</Descrizione>
        <Quantita>3.00</Quantita>
        <UnitaMisura>CT</UnitaMisura>
        <PrezzoUnitario>28.80</PrezzoUnitario>
        <PrezzoTotale>86.40</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""",

        # 5. Nota di Credito TD04 (Storno / Reso fusti da Partesa)
        "NotaCredito_05_Partesa_Reso_Fusti.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>05012340158</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>PAR2026-NC0089</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>SUBM70N</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>05012340158</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>05012340158</CodiceFiscale>
        <Anagrafica>
          <Denominazione>PARTESA S.P.A.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Edison 15</Indirizzo>
        <CAP>20090</CAP>
        <Comune>Assago</Comune>
        <Provincia>MI</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>02562290227</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>02562290227</CodiceFiscale>
        <Anagrafica>
          <Denominazione>GESTIONI LOCALI S.R.L. - KRUGEL</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Nazionale</Indirizzo>
        <CAP>38015</CAP>
        <Comune>Lavis</Comune>
        <Provincia>TV</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD04</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{d_curr}</Data>
        <Numero>NC-2026/0112</Numero>
        <ImportoTotaleDocumento>107.60</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
      <DatiTrasporto>
        <DatiIndirizzoResa>
          <Indirizzo>Via Nazionale (Krügel)</Indirizzo>
          <CAP>38015</CAP>
          <Comune>Lavis</Comune>
          <Provincia>TV</Provincia>
        </DatiIndirizzoResa>
      </DatiTrasporto>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>BIR-HEIN-30L</CodiceValore>
        </CodiceArticolo>
        <Descrizione>STORNO PER RESO HEINEKEN BIRRA FUSTO 30LT</Descrizione>
        <Quantita>1.00</Quantita>
        <UnitaMisura>FUSTO</UnitaMisura>
        <PrezzoUnitario>88.20</PrezzoUnitario>
        <PrezzoTotale>88.20</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""",

        # 6. Fattura DA ASSEGNARE (Metro Cash & Carry - senza indirizzo di consegna univoco)
        "Fattura_06_Metro_Da_Assegnare.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>00816390153</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>METRO2026-44021</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>SUBM70N</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>00816390153</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>00816390153</CodiceFiscale>
        <Anagrafica>
          <Denominazione>METRO ITALIA CASH AND CARRY S.P.A.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via XXV Aprile 23</Indirizzo>
        <CAP>20097</CAP>
        <Comune>San Donato Milanese</Comune>
        <Provincia>MI</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>02562290227</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>02562290227</CodiceFiscale>
        <Anagrafica>
          <Denominazione>GESTIONI LOCALI S.R.L.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Tamarisi 2</Indirizzo>
        <CAP>38015</CAP>
        <Comune>Lavis</Comune>
        <Provincia>TV</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{d_curr}</Data>
        <Numero>FT-METRO-09881</Numero>
        <ImportoTotaleDocumento>309.88</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>EAN</CodiceTipo>
          <CodiceValore>8001234567890</CodiceValore>
        </CodiceArticolo>
        <Descrizione>TOVAGLIOLI BAR 2 VELI BIANCHI CT 2000PZ</Descrizione>
        <Quantita>4.00</Quantita>
        <UnitaMisura>CT</UnitaMisura>
        <PrezzoUnitario>19.50</PrezzoUnitario>
        <PrezzoTotale>78.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>EAN</CodiceTipo>
          <CodiceValore>8009876543210</CodiceValore>
        </CodiceArticolo>
        <Descrizione>OLIO EXTRAVERGINE DI OLIVA LATTA 5LT</Descrizione>
        <Quantita>2.00</Quantita>
        <UnitaMisura>LT</UnitaMisura>
        <PrezzoUnitario>46.00</PrezzoUnitario>
        <PrezzoTotale>92.00</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>3</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>DET-LAV-IND</CodiceValore>
        </CodiceArticolo>
        <Descrizione>DETERGENTE LAVASTOVIGLIE BAR TANICA 12KG</Descrizione>
        <Quantita>3.00</Quantita>
        <UnitaMisura>PZ</UnitaMisura>
        <PrezzoUnitario>28.00</PrezzoUnitario>
        <PrezzoTotale>84.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""",

        # 7. Fattura Partesa di 4 mesi fa (per calcolo min/max e prezzo medio ponderato)
        "Fattura_07_Partesa_Krugel_Prezzi_Precedenti.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>05012340158</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>PAR2026-001198</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>SUBM70N</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>05012340158</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>05012340158</CodiceFiscale>
        <Anagrafica>
          <Denominazione>PARTESA S.P.A.</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Edison 15</Indirizzo>
        <CAP>20090</CAP>
        <Comune>Assago</Comune>
        <Provincia>MI</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>02562290227</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>02562290227</CodiceFiscale>
        <Anagrafica>
          <Denominazione>GESTIONI LOCALI S.R.L. - KRUGEL PUB</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Nazionale</Indirizzo>
        <CAP>38015</CAP>
        <Comune>Lavis</Comune>
        <Provincia>TV</Provincia>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{d_4m}</Data>
        <Numero>FT-2026/0284</Numero>
        <ImportoTotaleDocumento>846.68</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
      <DatiTrasporto>
        <DatiIndirizzoResa>
          <Indirizzo>Via Nazionale</Indirizzo>
          <CAP>38015</CAP>
          <Comune>Lavis</Comune>
          <Provincia>TV</Provincia>
        </DatiIndirizzoResa>
      </DatiTrasporto>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>BIR-HEIN-30L</CodiceValore>
        </CodiceArticolo>
        <Descrizione>HEINEKEN BIRRA FUSTO 30LT</Descrizione>
        <Quantita>5.00</Quantita>
        <UnitaMisura>FUSTO</UnitaMisura>
        <PrezzoUnitario>98.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>6.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>460.60</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>BIR-ICHN-30L</CodiceValore>
        </CodiceArticolo>
        <Descrizione>ICHNUSA NON FILTRATA FUSTO 30L</Descrizione>
        <Quantita>2.00</Quantita>
        <UnitaMisura>FUSTO</UnitaMisura>
        <PrezzoUnitario>105.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>5.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>199.50</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>3</NumeroLinea>
        <CodiceArticolo>
          <CodiceTipo>FORN</CodiceTipo>
          <CodiceValore>BIR-COR-24BT</CodiceValore>
        </CodiceArticolo>
        <Descrizione>CORONA EXTRA CT 24 BOTTIGLIE 33CL</Descrizione>
        <Quantita>2.00</Quantita>
        <UnitaMisura>CT</UnitaMisura>
        <PrezzoUnitario>24.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>8.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>44.16</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""
    }

    created_paths = []
    for fname, content in xml_files.items():
        fpath = os.path.join(DEMO_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content.strip())
        created_paths.append(fpath)

    return created_paths

def load_demo_data_into_db(conn: sqlite3.Connection):
    """Importa tutti i file XML demo nel database utilizzando il parser e l'engine ufficiali"""
    xml_paths = generate_demo_xmls()
    results = []
    for p in xml_paths:
        fname = os.path.basename(p)
        with open(p, "rb") as f:
            content = f.read()
        res = XmlFileImporter.process_file_bytes(conn, content, fname)
        results.append(res)
    return results
