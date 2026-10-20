"""Free licensed Wikimedia audio discovery/download. No keys, purchases or account."""
import datetime as dt
import hashlib
import html
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import requests
from .core import digest,write_json
from .pipeline import validate_free_audio_asset

API='https://commons.wikimedia.org/w/api.php'
LICENSES={'https://creativecommons.org/publicdomain/zero/1.0/':'CC0-1.0',
          'https://creativecommons.org/licenses/by/4.0/':'CC-BY-4.0'}
HEADERS={'User-Agent':'MicroDrama-local-audio/1.0 (private offline film preparation)'}


def text(value):
    return html.unescape(re.sub('<[^>]*>','',value)).strip()


def metadata_candidate(page):
    info=page['imageinfo'][0];meta=info.get('extmetadata',{})
    value=lambda k:text(meta.get(k,{}).get('value',''))
    license_url=value('LicenseUrl').replace('http://','https://')
    if not license_url.endswith('/'):license_url+='/'
    if license_url not in LICENSES or value('LicenseShortName') not in ('CC0','CC0 1.0','CC BY 4.0'):return None
    if value('Restrictions') or value('NonFree').lower()=='true':return None
    url=info.get('url','');source=info.get('descriptionurl','');mime=info.get('mime','')
    if urlparse(url).scheme!='https' or urlparse(url).hostname!='upload.wikimedia.org' or not mime.startswith('audio/'):return None
    if urlparse(source).scheme!='https' or urlparse(source).hostname!='commons.wikimedia.org':return None
    artist=value('Artist')
    if not artist:return None
    return {'page_id':page['pageid'],'title':page['title'],'creator':artist,'license':LICENSES[license_url],
            'license_url':license_url,'source_url':source,'download_url':url,'mime':mime,'size':info.get('size'),
            'description':value('ImageDescription'),'source_metadata':info}


class CommonsAudio:
    def __init__(self,http=None):self.http=http or requests.Session()
    def search(self,query,limit=10):
        if not isinstance(query,str) or not query.strip() or len(query)>200:raise ValueError('Short audio query required')
        if type(limit) is not int or not 1<=limit<=20:raise ValueError('Result limit 1..20 required')
        r=self.http.get(API,params={'action':'query','format':'json','generator':'search','gsrsearch':query+' filetype:audio',
            'gsrnamespace':6,'gsrlimit':limit,'prop':'imageinfo','iiprop':'url|mime|size|extmetadata','iiextmetadatalanguage':'en'},
            headers=HEADERS,timeout=30,allow_redirects=False)
        r.raise_for_status()
        if r.status_code!=200:raise ValueError('Search redirect/status refused')
        results=[]
        for page in r.json().get('query',{}).get('pages',{}).values():
            try:c=metadata_candidate(page)
            except (KeyError,IndexError,TypeError):c=None
            if c:results.append(c)
        return results
    def refresh(self,page_id):
        if type(page_id) is not int or page_id<1:raise ValueError('Verified Commons page ID required')
        r=self.http.get(API,params={'action':'query','format':'json','pageids':page_id,'prop':'imageinfo','iiprop':'url|mime|size|extmetadata'},headers=HEADERS,timeout=30,allow_redirects=False)
        r.raise_for_status()
        if r.status_code!=200:raise ValueError('Metadata redirect/status refused')
        c=metadata_candidate(r.json()['query']['pages'][str(page_id)])
        if c is None:raise ValueError('Current free commercial-compatible license not verified')
        return c
    def download(self,candidate,output,max_bytes=30*1024*1024):
        current=self.refresh(candidate['page_id'])
        for key in ('license','license_url','download_url','creator'):
            if current[key]!=candidate[key]:raise ValueError('Audio metadata changed; choose again')
        if type(max_bytes) is not int or not 1<=max_bytes<=30*1024*1024:raise ValueError('Maximum download cap is 30 MiB')
        if type(current['size']) is not int or not 0<current['size']<=max_bytes:raise ValueError('Audio size unknown or too large')
        root=Path(output)
        if root.exists():raise ValueError('Fresh audio asset directory required')
        # Only fixed Creative Commons terms and upload.wikimedia.org bytes, never metadata-selected arbitrary hosts.
        terms=self.http.get(current['license_url'],headers=HEADERS,timeout=30,allow_redirects=False);terms.raise_for_status()
        if terms.status_code!=200:raise ValueError('License terms not directly retrievable')
        license_text=terms.text
        if len(license_text)>2*1024*1024:raise ValueError('License terms page too large')
        if ('CC0' if current['license']=='CC0-1.0' else 'Attribution 4.0') not in license_text:raise ValueError('License page content does not confirm expected license')
        r=self.http.get(current['download_url'],headers=HEADERS,stream=True,timeout=60,allow_redirects=False);r.raise_for_status()
        if r.status_code!=200:raise ValueError('Audio download redirected or unavailable')
        root.mkdir(parents=True);pending=root/'source.pending';total=0
        try:
            with pending.open('xb') as f:
                for block in r.iter_content(65536):
                    total+=len(block)
                    if total>max_bytes:raise ValueError('Audio exceeds download cap')
                    f.write(block)
            if total!=current['size']:raise ValueError('Downloaded size differs from current metadata')
            info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(pending)],text=True))
            if not info['streams'] or any(s['codec_type']!='audio' for s in info['streams']):raise ValueError('Download is not audio-only')
            audio=root/'audio.wav'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(pending),'-vn','-c:a','pcm_s16le',str(audio)],check=True,capture_output=True)
            if float(info['streams'][0].get('duration',0) or 0)>1800:raise ValueError('Source audio exceeds 30-minute safety cap')
            license_path=root/'license-terms.html';license_path.write_text(license_text)
            attribution=f"{current['title']} by {current['creator']} | {current['license']} | {current['source_url']} | {current['license_url']} | Converted to WAV; may be mixed/trimmed"
            asset={'path':str(audio.resolve()),'sha256':digest(audio),'title':current['title'],'creator':current['creator'],
                'source_url':current['source_url'],'license_url':current['license_url'],'license':current['license'],
                'license_checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'license_terms_path':str(license_path.resolve()),
                'license_terms_sha256':digest(license_path),'commercial_use_verified':True,'sync_use_verified':True,'attribution':attribution,
                'rights_caveat':'Commons contributor metadata, not independent title clearance; reject additional restrictions/unclear identity/content',
                'source_audio_sha256':digest(pending),'status':'downloaded_licensed_candidate_requires_content_listening'}
            validate_free_audio_asset(asset);write_json(root/'asset.json',asset);(root/'ATTRIBUTION.txt').write_text(attribution+'\n');write_json(root/'source-metadata.json',current)
            return asset
        except Exception:
            import shutil;shutil.rmtree(root);raise
        finally:
            r.close()
            if pending.exists():pending.unlink()
    def choose_and_download(self,query,output,selector=None):
        results=self.search(query)
        if not results:raise ValueError('No compatible free-license audio found; do not substitute paid/unclear audio')
        # Keyword order is discovery ranking, not proof that a track matches a scene.
        index=selector(results) if selector else 0
        if type(index) is not int or not 0<=index<len(results):raise ValueError('Invalid audio selection')
        return self.download(results[index],output)
