"""Fixture helper: data/french/rates.json with the monthly risk-free rate (RF) and a daily calendar, in the French library's file formats.
Used by engine and product tests whose real-market fixtures need the cash rate (owner, 2 November 2026, fix 2)."""
import hashlib
import io
import json
import zipfile

NL=chr(10)
NOTE='This file was created by using the 202609 CRSP database.'
COPYRIGHT='Copyright 2026 Eugene F. Fama and Kenneth R. French'


def zipped(path,name,text):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z: z.writestr(name,text)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(buffer.getvalue());return hashlib.sha256(buffer.getvalue()).hexdigest()


def monthly_csv(months,rf):
    return NL.join([NOTE,'',',Mkt-RF,SMB,HML,RF']+[f'{m},{0:8.2f},{0:8.2f},{0:8.2f},{rf:8.2f}' for m in months]+
                   ['','  Annual Factors: January-December ',',Mkt-RF,SMB,HML,RF','  1950,    1.00,    0.00,    0.00,    3.00','',COPYRIGHT])+NL


def daily_csv(days):
    return NL.join([NOTE,'',',Mkt-RF,SMB,HML,RF']+[f'{d},{0:8.2f},{0:8.2f},{0:8.2f},{0.01:8.2f}' for d in days]+['',COPYRIGHT])+NL


def rates_file(root,days,rf=0.30,months=None):
    """The monthly RF of every month of days (percent per month), and days (ISO or YYYYMMDD) as the daily calendar."""
    days=sorted({d.replace('-','') for d in days});months=months if months is not None else sorted({d[:6] for d in days})
    msha=zipped(root/'data'/'french'/'raw'/'ffm.zip','F-F_Research_Data_Factors.csv',monthly_csv(months,rf))
    dsha=zipped(root/'data'/'french'/'raw'/'ffc.zip','F-F_Research_Data_Factors_daily.csv',daily_csv(days))
    body={'schema_version':'1','kind':'french-rates','monthly':{'path':'data/french/raw/ffm.zip','sha256':msha},
          'calendar':{'path':'data/french/raw/ffc.zip','sha256':dsha}}
    (root/'data'/'french'/'rates.json').write_text(json.dumps(body),encoding='utf-8')
