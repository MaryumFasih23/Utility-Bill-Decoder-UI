import io
import json
import logging
from pathlib import Path
from PIL import Image, ImageOps
from schemas import Extraction, Bill, RawEvidence, FactPatch, HistoricalEvidence
from prompts import EXTRACTION_PROMPT, EVIDENCE_PROMPT, PROMPT_VERSION
from storage import Cache, digest
from validation import reliability, check_private
from evidence import materialize_evidence, evidence_checks, canonicalize_signs

log = logging.getLogger(__name__)

def source_images(path, boxes=(), max_side: int = 3072):
    """EXIF orientation; preserve original aspect ratio; cap huge scan dimensions to max_side."""
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
        if max(image.size) > max_side:
            ratio = max_side / max(image.size)
            image = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format='PNG')
        images = [(output.getvalue(), 'image/png')]
        for box in list(boxes)[:4]:
            w, h = image.size
            left, top, right, bottom = box
            crop = image.crop((max(0, int((left-.015)*w)), max(0, int((top-.015)*h)),
                               min(w, int((right+.015)*w)), min(h, int((bottom+.015)*h))))
            if max(crop.size) < 1600:
                factor = min(3, 1600 / max(crop.size))
                crop = crop.resize((int(crop.width*factor), int(crop.height*factor)), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            crop.save(buf, format='PNG')
            images.append((buf.getvalue(), 'image/png'))
        return images

class Extractor:
    def __init__(self, settings, client, no_cache=False, verifier=None):
        self.settings, self.client, self.verifier = settings, client, verifier
        self.cache = Cache(settings.cache_dir / 'extractions', not no_cache)
        self.verify_cache = Cache(settings.cache_dir / 'verification', not no_cache)

    def extract(self, path: Path, focus=''):
        key = digest(path.read_bytes(), self.settings.model, PROMPT_VERSION,
                     json.dumps(Extraction.model_json_schema(), sort_keys=True), focus,
                     self.settings.verification, self.settings.verification_model)
        cached = self.cache.get(key, Extraction)
        if cached is not None:
            # Repair the former null-overlap merge defect using retained runtime facts.
            catalog={f.id:f for f in cached.evidence.facts}
            for row in cached.evidence.history:
                for kind in ('units','billed','payment'):
                    ref=getattr(row,kind+'_fact')
                    if ref and catalog[ref].value is None:
                        alternatives=[f for f in cached.evidence.facts
                            if f.label==row.month_label+' '+kind and f.value is not None]
                        if len(alternatives)==1:
                            fact=alternatives[0]
                            if fact.confidence=='low': fact.confidence='medium'
                            setattr(row,kind+'_fact',fact.id)
            if sum(bool(r.units_fact) for r in cached.evidence.history)<12:
                cached=self.recover_history(path,cached)
                self.cache.put(key,cached)
            return canonicalize_signs(cached)
        max_side = getattr(self.settings, 'max_image_side', 3072)
        images = source_images(path, max_side=max_side)
        prompt = EXTRACTION_PROMPT + '\nFor this stage return ONLY the Bill schema. Rich evidence is extracted in a separate stage.\nSpecial recovery focus: ' + focus
        bill = self.client.generate(prompt, Bill, images)
        requested = [name for name,value in bill.model_dump().items() if value is not None and name not in ('charges','taxes')]
        requested += [f'charge_{i}' for i in range(len(bill.charges))] + [f'tax_{i}' for i in range(len(bill.taxes))]
        line_mapping = [{'id':f'charge_{i}','type':item.type} for i,item in enumerate(bill.charges)]
        line_mapping += [{'id':f'tax_{i}','type':item.type} for i,item in enumerate(bill.taxes)]
        # Do not pass monetary predictions to independent evidence reading: avoid anchoring.
        evidence_prompt = EVIDENCE_PROMPT + '\nRequired scalar/line fact IDs (read values independently from image):\n' + json.dumps(requested) + '\nLine classifications for ID mapping only, NO predicted amounts:\n' + json.dumps(line_mapping) + '\nSpecial recovery focus: ' + focus
        evidence = materialize_evidence(self.client.generate(evidence_prompt, RawEvidence, images))
        result = Extraction(bill=bill, evidence=evidence)
        if sum(bool(r.units_fact) for r in evidence.history)<12:
            result=self.recover_history(path,result)
            evidence=result.evidence
        warnings = reliability(result, path.name)
        difficult = evidence_checks(result)
        difficult += [f.id+': uncertain source fact' for f in evidence.facts
                      if f.confidence in ('low','unreadable') and not f.id.startswith('history_cell_')]
        if difficult:
            boxes = [f.bbox for f in result.evidence.facts if f.bbox and f.confidence in ('low', 'unreadable')]
            patch_ids=sorted({issue.split(':',1)[0] for issue in difficult})
            reread = 'Reread ONLY these requested source facts from this bill image. Return FactPatch. Each Fact.id MUST be exactly one of the IDs in the list below (no spaces or appended messages). Use visible printed text and source sections. Numeric values are printed strings, dates are ISO. Provider value is normalized KE, IESCO or LESCO. total_charges is the printed electricity/net electricity subtotal, NOT current_bill/grand total. Do not add FPA to create a subtotal. Do not recalculate amounts or copy identifiers. Null for unreadable.\nExact fact IDs:\n' + json.dumps(patch_ids) + '\nLine type mapping (no amounts):\n' + json.dumps(line_mapping)
            try:
                patch = self.client.generate(reread, FactPatch, source_images(path, boxes, max_side=max_side))
                facts = {f.id:f for f in evidence.facts}
                facts.update({f.id:f for f in patch.facts})
                evidence = evidence.model_copy(update={'facts':list(facts.values())})
                result = Extraction(bill=bill, evidence=evidence)
            except RuntimeError as exc:
                log.warning('Targeted reread unavailable: %s; keeping original extraction and warnings.', exc)
        # A combined Taxes line is not a separately named other_tax line.
        if len(bill.taxes)==1 and bill.taxes[0].type=='other_tax':
            tax_fact=next((f for f in evidence.facts if f.id=='tax_0'),None)
            if tax_fact and tax_fact.label.strip().lower() in ('taxes','total taxes','combined taxes','taxes and duties'):
                bill=bill.model_copy(update={'taxes':[]})
                result=Extraction(bill=bill,evidence=evidence)
        conflicts = [w for w in evidence_checks(result) if 'official field conflicts' in w or 'line amount conflicts' in w]
        if conflicts:
            # Extraction correction by image reread, never arithmetic reconciliation.
            reread_bill = prompt + '\nIndependent image evidence conflicts with preliminary fields. Reread ONLY printed values; do not sum or reconcile.\nConflicts:\n' + json.dumps(conflicts) + '\nSource observations:\n' + evidence.model_dump_json()
            try:
                bill = self.client.generate(reread_bill, Bill, images)
                result = Extraction(bill=bill,evidence=evidence)
            except RuntimeError:
                log.warning('Conflicting field reread unavailable; uncertainties recorded.')
        # A fact conflicting with the official extraction cannot support a confident answer.
        for issue in evidence_checks(result):
            if 'conflicts' in issue:
                fid = issue.split(':',1)[0]
                for fact in result.evidence.facts:
                    if fact.id == fid: fact.confidence='low'
                result.evidence.ambiguities.append(issue)
        if self.verifier and any(f.confidence in ('low', 'unreadable') for f in result.evidence.facts):
            verified = self.verify_cache.get(key, Extraction)
            if verified is None:
                verified = self.verifier.verify(EXTRACTION_PROMPT, Extraction, images)
                if verified: self.verify_cache.put(key, verified)
            if verified:
                result = self.resolve_conflicts(path, result, verified)
        result = canonicalize_signs(result)
        # Privacy is checked on internal evidence as well as official JSON.
        check_private(result.model_dump_json(), [self.settings.primary, self.settings.backup, self.settings.openai_key])
        self.cache.put(key, result)
        return result

    def recover_history(self,path,result):
        prompt='''Transcribe ONLY historical charts and tables from this bill image.
Return HistoricalEvidence, with direct printed strings in units, billed and payment.
Include EVERY bar of any 13-month usage chart, including the black current-month bar.
Read vertical digits on bars carefully. The three-row payment table is NOT the usage
chart. Include both; year headings establish exact calendar month. Two-block tables
have six months in EACH block, including the first row under the header. Align each
month and its own units/billed/payment, never shift rows. Do not calculate or guess.
Keep chart rows separate from table rows; Python merges exact same year/month.
Include missing cells as null, unreadable visible cells in unreadable_cells. Do not
include identifiers. Capture every row before marking history_complete true.'''
        tiles=[(0.0,0.0,1.0,0.4),(0.0,0.3,1.0,0.7),(0.0,0.6,1.0,1.0)]
        history_cache=Cache(self.settings.cache_dir/'history_recovery',self.cache.enabled)
        history_key=digest(path.read_bytes(),self.settings.model,prompt)
        history=history_cache.get(history_key,HistoricalEvidence)
        if history is None:
            history=self.client.generate(prompt,HistoricalEvidence,source_images(path,tiles))
            history_cache.put(history_key,history)
        retained=[f for f in result.evidence.facts if not f.id.startswith('history_cell_')]
        raw=RawEvidence(facts=retained,history=history.history,
            history_complete=history.history_complete,net_metering=result.evidence.net_metering,
            missing=result.evidence.missing,ambiguities=result.evidence.ambiguities)
        return Extraction(bill=result.bill,evidence=materialize_evidence(raw))

    def resolve_conflicts(self, path, primary, secondary):
        # Request a source reread, never blindly accept another model's value.
        conflicts = [key for key in type(primary.bill).model_fields if getattr(primary.bill, key) != getattr(secondary.bill, key)]
        if not conflicts: return primary
        prompt = EXTRACTION_PROMPT + '\nIndependent extractions disagree. Reinspect image; return null for genuinely unresolved fields.\nFields: ' + ', '.join(conflicts) + '\nA:\n' + primary.model_dump_json() + '\nB:\n' + secondary.model_dump_json()
        try: return self.client.generate(prompt, Extraction, source_images(path))
        except RuntimeError:
            data = primary.model_dump(mode='json')
            for name in conflicts:
                data['bill'][name] = [] if name in ('charges', 'taxes') else None
                for f in data['evidence']['facts']:
                    if f['id'] == name or (name in ('charges', 'taxes') and f['id'].startswith(name[:-1] + '_')):
                        f['value'], f['confidence'] = None, 'unreadable'
            data['evidence']['ambiguities'].append('Unresolved independent-model disagreement: ' + ', '.join(conflicts))
            return Extraction.model_validate(data)
