import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from simulator_service import Simulator, UnavailableModel
from demo_access import token_hash
from fastapi.testclient import TestClient
from test_wallet import ModelFixture


class AccessEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.service = Simulator(':memory:', ModelFixture())
        self.world = self.service.create_world('payer', 42, 'investment')
        self.wid = self.world['id']

    def tearDown(self):
        self.service.db.close()

    def review(self, amount=20_000_000):
        p = self.service.intent(self.wid, 'payer', 4, amount)
        return p, self.service.review(self.wid, 'payer', p['id'])

    def test_observer_scope_expiry_revocation_and_hash_only_storage(self):
        token = self.service.share(self.wid, 'payer', 4)['token']
        view = self.service.observe(token)
        self.assertEqual([a['id'] for a in view['accounts']], [4])
        self.assertNotIn('intents', view)
        stored = self.service.db.execute('SELECT id FROM sim_access').fetchall()
        self.assertIn(token_hash(token), [r[0] for r in stored])
        self.assertNotIn(token, json.dumps([dict(r) for r in stored]))
        with patch('demo_access.time.time', return_value=10**12):
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.service.observe(token)
        self.service.revoke_sharing(self.wid, 'payer')
        with self.assertRaisesRegex(ValueError, 'revoked'):
            self.service.observe(token)

    def test_contact_consent_durable_inbox_ack_is_not_authorization(self):
        self.service.contact_consent(self.wid, 'payer', True)
        token = self.service.provision(self.wid, 'contact')['token']
        p, r = self.review()
        self.assertEqual(len(self.service.role_view(token)['alerts']), 1)
        self.service.review(self.wid, 'payer', p['id'])
        self.assertEqual(len(self.service.role_view(token)['alerts']), 1)
        self.service.role_action(token, 'acknowledge')
        self.assertEqual(self.service.role_view(token)['alerts'], [])
        with self.assertRaisesRegex(ValueError, 'Role'):
            self.service.role_action(token, 'approve', p['id'], r['id'])
        self.service.contact_consent(self.wid, 'payer', False)
        with self.assertRaises(ValueError):
            self.service.role_view(token)

    def test_analyst_approval_bound_to_review_not_only_revision(self):
        p, r = self.review()
        self.service.control(self.wid, 'payer', 'advance', seconds=3600)
        fresh = self.service.review(self.wid, 'payer', p['id'])
        token = self.service.provision(self.wid, 'analyst')['token']
        self.service.role_action(token, 'approve', p['id'], fresh['id'])
        newer = self.service.review(self.wid, 'payer', p['id'])
        with self.assertRaisesRegex(ValueError, 'analyst'):
            self.service.execute(self.wid, 'payer', p['id'], newer['id'], True, 'DEMO')
        self.service.role_action(token, 'approve', p['id'], newer['id'])
        result = self.service.execute(self.wid, 'payer', p['id'], newer['id'], True, 'DEMO')
        self.assertEqual(result['state'], 'completed')

    def test_failed_model_records_correlated_error_and_no_settlement(self):
        p, _ = self.review(10000)
        self.service.model = UnavailableModel()
        with self.assertRaises(RuntimeError):
            self.service.review(self.wid, 'payer', p['id'])
        failed = [e for e in self.service.events(self.wid, 'payer') if e['stage'] == 'review_failed']
        self.assertEqual(failed[-1]['failed_stage'], 'model_scored')
        self.assertTrue(failed[-1]['evaluation_id'])
        self.assertFalse(self.service.read_world(self.wid, 'payer')['transfers'])

    def test_witness_sources_are_real_and_probe_terms_recompute(self):
        w = self.service.create_world('payer', 27, 'probes')
        self.wid = w['id']
        _, r = self.review(10000)
        f = r['feature_snapshot']
        events = {e['id']:e for e in f['evidence']}
        from risk_common import FEATURE_COLUMNS
        self.assertEqual(len(f['lineage']['features']), len(FEATURE_COLUMNS))
        for fact in f['lineage']['features'].values():
            for eid in fact['event_ids'] + fact.get('report_ids', []):
                self.assertIn(eid, events)
                self.assertLess(events[eid]['event_at'], r['evaluated_at'])
                self.assertLess(events[eid]['available_at'], r['evaluated_at'])
        probes = f['lineage']['features']['pi_t_snd']
        self.assertEqual(probes['value'], len(probes['event_ids']))
        self.assertEqual(probes['calculation']['qualifying_count'], 3)

    def test_counterfactual_forks_world_and_preserves_original(self):
        p, original = self.review()
        before = copy.deepcopy(self.service._world(self.wid, 'payer'))
        changed = self.service.counterfactual(self.wid, 'payer', original['id'])
        self.assertNotEqual(changed['world'], self.wid)
        self.assertEqual(before, self.service._world(self.wid, 'payer'))
        self.assertEqual(original, self.service.replay(self.wid, 'payer', original['id'], True))
        self.assertEqual(changed['review']['counterfactual_of']['review'], original['id'])

    def test_purge_removes_reviews_grants_and_ledger(self):
        p, r = self.review()
        token = self.service.provision(self.wid, 'analyst')['token']
        self.service.delete_world(self.wid, 'payer')
        for table in ('sim_access','sim_review','sim_event','sim_ledger','sim_intent'):
            self.assertEqual(self.service.db.execute(f'SELECT COUNT(*) FROM {table} WHERE world=?',(self.wid,)).fetchone()[0], 0)
        with self.assertRaises(ValueError):
            self.service.role_view(token)

    def test_provider_unavailable_stays_unknown_and_cannot_file(self):
        p, r = self.review()
        self.assertTrue(all(x['verdict'] == 'unknown' for x in r['feature_snapshot']['providers'].values()))
        token = self.service.provision(self.wid, 'analyst')['token']
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.service.role_action(token, 'file_report', p['id'], r['id'])

    def test_transaction_rollback_does_not_publish_event(self):
        before = self.service.events(self.wid, 'payer')
        with self.assertRaises(RuntimeError):
            with self.service.transaction():
                self.service._event(self.wid, 'must_not_publish')
                raise RuntimeError('rollback')
        self.assertEqual(before, self.service.events(self.wid, 'payer'))

    def test_export_verification_and_tampering(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        from verify_bundle import verify
        p, r = self.review(10000)
        bundle = self.service.bundle(self.wid, 'payer', r['id'])
        self.assertTrue(verify(bundle)['verified'])
        bundle['review']['payment']['amount_paise'] += 1
        with self.assertRaises((AssertionError, ValueError)):
            verify(bundle)

    def test_tuning_and_calibration_days_are_disjoint(self):
        import pandas as pd
        from risk_common import carve_calib
        df=pd.DataFrame([dict(split='val',day=d) for d in range(18,24)])
        df = carve_calib(df)
        tuning, calibration=df[df.split=='val'], df[df.split=='calib']
        self.assertLess(tuning.day.max(), calibration.day.min())
        self.assertFalse(set(tuning.index) & set(calibration.index))


