"""Download the selected public synthetic mobile-money dataset, never banking records."""
import hashlib
import json
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
URL='https://www.kaggle.com/api/v1/datasets/download/ealaxi/paysim1'

if __name__=='__main__':
    directory=ROOT/'data/v4/paysim'
    directory.mkdir(parents=True,exist_ok=True)
    archive=directory/'source.zip'
    if not archive.exists():
        temporary=directory/'download.part'
        with urllib.request.urlopen(URL,timeout=60) as response,temporary.open('wb') as out:
            shutil.copyfileobj(response,out)
        temporary.replace(archive)
    with zipfile.ZipFile(archive) as z:
        candidates=[i for i in z.infolist() if i.filename.lower().endswith('.csv')]
        if len(candidates)!=1 or candidates[0].file_size>2_000_000_000:
            raise ValueError('Unexpected archive; no files extracted')
        target=directory/'transactions.csv'
        with z.open(candidates[0]) as source,target.open('wb') as out:
            shutil.copyfileobj(source,out)
    def checksum(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    manifest=dict(source='https://www.kaggle.com/datasets/ealaxi/paysim1',creator='https://github.com/EdgarLopezPhD/PaySim',
                  acquired_at=time.time(),dataset='PaySim1',data_kind='public synthetic mobile-money; not UPI',
                  license='CC BY-SA 4.0 per selected distribution; retain attribution and terms',
                  archive_sha256=checksum(archive),csv_sha256=checksum(target),bytes=target.stat().st_size)
    (directory/'source-manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Downloaded public PaySim data; checksums and attribution recorded in',directory)
