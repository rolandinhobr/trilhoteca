import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_library as fixtures
from search_engine import profile, interpret
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bs4 import BeautifulSoup
from collect_sfx import oga_sfx_records, valid_member, make_record


class SceneSearchTests(unittest.TestCase):
    setUp = fixtures.LibraryTests.setUp
    tearDown = fixtures.LibraryTests.tearDown
    mutate = fixtures.LibraryTests.mutate

    def test_partial_match_is_never_presented_as_satisfying_complete_brief(self):
        result = self.lib.search(self.pid, 'piano suspense crescente')
        self.assertEqual(result['assets'], [])
        self.assertEqual(result['alternatives'][0]['scene_match']['missing'], ['suspense','crescendo','criar tensão'])
        self.assertEqual(result['alternatives'][0]['scene_match']['fit'], 'partial')

    def test_all_requested_concepts_are_combined(self):
        self.mutate(tags=['piano','dark','build up'])
        result = self.lib.search(self.pid, 'piano suspense crescente')
        self.assertEqual(result['total'],1)
        self.assertEqual(result['assets'][0]['scene_match']['missing'],[])

    def test_unknown_voice_and_duration_are_only_included_explicitly(self):
        self.mutate(vocals=None, duration=None)
        self.assertEqual(self.lib.search(self.pid,'piano sem voz',duration_min=20)['total'],0)
        result=self.lib.search(self.pid,'piano sem voz',duration_min=20,allow_unknown=True)
        self.assertEqual(result['total'],1)
        self.assertEqual(len(result['assets'][0]['scene_match']['pending']),2)

    def test_explicit_exclusion_is_not_silently_relaxed(self):
        self.assertEqual(self.lib.search(self.pid,'piano',exclude=['piano'])['total'],0)
        self.assertEqual(self.lib.search(self.pid,'sem piano')['total'],0)

    def test_false_sem_voz_allows_both_instrumental_and_vocal(self):
        self.assertEqual(self.lib.search(self.pid,'piano',no_voice=False)['total'],1)

    def test_negated_source_signals_do_not_become_positive_facets(self):
        self.mutate(title='Example',tags=[],description='No drums, not loopable, gentle piano.')
        p=profile(self.lib.asset(self.asset['id']))['facets']
        self.assertNotIn('percussao',p);self.assertNotIn('loop',p)
        self.assertIn('piano',p)

    def test_ui_is_a_word_not_a_substring_of_building(self):
        self.mutate(title='Building',tags=[],description='Building tension.')
        self.assertNotIn('interface',profile(self.lib.asset(self.asset['id']))['facets'])

    def test_scene_batch_retains_scene_identity_and_context(self):
        result=self.lib.search_scenes(self.pid,[{'nome':'Fala','pedido':'piano calmo','funcao':'narracao'},{'nome':'Corte','pedido':'whoosh','tipo':'sfx'}])
        self.assertEqual([s['name'] for s in result['scenes']],['Fala','Corte'])
        self.assertEqual(result['scenes'][0]['total'],1)
        self.assertEqual(result['scenes'][1]['total'],0)
        self.assertTrue(self.lib.search_scenes(None,[{'pedido':'piano'}])['needs_context'])

    def test_sound_effect_duration_and_object_are_hard_requirements(self):
        self.mutate(kind='sfx',title='impactMetal001',tags=[],description='',search_text='impactMetal001',duration=.4)
        self.assertEqual(self.lib.search(self.pid,'impacto metal',duration_max=.5)['total'],1)
        self.assertEqual(self.lib.search(self.pid,'impacto metal',duration_max=.2)['total'],0)
        self.assertEqual(self.lib.search(self.pid,'impacto madeira')['total'],0)

    def test_short_track_only_covers_longer_scene_when_loop_is_declared(self):
        self.mutate(duration=10)
        self.assertEqual(self.lib.search(self.pid,'piano',scene_seconds=30)['total'],0)
        self.mutate(tags=['piano','loop'])
        self.assertEqual(self.lib.search(self.pid,'piano',scene_seconds=30)['total'],1)

    def test_invalid_duration_is_rejected(self):
        for v in [float('nan'),float('inf'),-1,True]:
            with self.assertRaises(ValueError):self.lib.search(self.pid,'piano',duration_max=v)
        with self.assertRaises(ValueError):self.lib.search(self.pid,'piano',duration_min=10,duration_max=2)

    def test_natural_seconds_are_parsed_without_spurious_unknown_tokens(self):
        request=interpret('whoosh 0,5 segundos')
        self.assertEqual(request['duration_max'],.5)
        self.assertEqual(request['uninterpreted_terms'],[])

    def test_mixed_pack_tags_do_not_label_each_member_as_all_objects(self):
        a=make_record(self.lib,'https://opengameart.org/content/mixed','Mixed Foley Pack','Author','Includes rain, door, footsteps.', ['rain','door','footsteps'], ['data/evidence/proof.txt'],'https://opengameart.org/mixed.zip','Footsteps/wood001.wav',.5)
        p=profile(a)['facets'];self.assertIn('passos',p);self.assertIn('madeira',p)
        self.assertNotIn('chuva',p);self.assertNotIn('porta',p)

    def test_collection_title_does_not_assign_all_surfaces_to_each_footstep(self):
        a=make_record(self.lib,'https://opengameart.org/content/steps','Different steps on wood, stone, leaves, gravel and mud','Author','',[],['data/evidence/proof.txt'],'https://opengameart.org/steps.zip','gravel.wav',.5)
        p=profile(a)['facets']
        self.assertIn('passos',p);self.assertIn('pedra',p);self.assertNotIn('madeira',p);self.assertNotIn('folhas',p)

    def test_footer_license_does_not_authorize_a_sound_pack(self):
        markup='<div class="node"><h2>Sound</h2><div class="field-name-author-submitter"><a class="username">Author</a></div></div><footer><a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a></footer>'
        with self.assertRaises(ValueError):oga_sfx_records(BeautifulSoup(markup,'html.parser'),markup.encode(),'https://opengameart.org/content/sound',self.root,self.lib)

    def test_unsafe_archive_members_are_ignored(self):
        import zipfile
        for filename in ['../evil.wav','/absolute.wav','__MACOSX/ghost.wav','.hidden.wav']:
            item=zipfile.ZipInfo(filename);item.file_size=100
            self.assertFalse(valid_member(item))

    def test_pack_encodings_are_deduplicated_and_duration_is_measured(self):
        import io,zipfile
        from collect_sfx import pack_entries
        pack=io.BytesIO()
        with zipfile.ZipFile(pack,'w') as z:
            z.writestr('WAV/step.wav',fixtures.wav())
            z.writestr('OGG/step.ogg',b'not the preferred encoding')
            z.writestr('../evil.wav',fixtures.wav())
        with patch.object(self.lib,'_fetch',side_effect=lambda url,dest:dest.write_bytes(pack.getvalue())):
            results=pack_entries('https://opengameart.org/test.zip',self.root,self.lib,'fixture')
        self.assertEqual(len(results),1)
        self.assertEqual(results[0][0],'WAV/step.wav')
        self.assertAlmostEqual(results[0][1],.1,places=2)

    def test_exact_copies_are_not_added_as_new_sounds(self):
        from discovery import merge_assets
        first=dict(self.asset,id='unique-hash-a',download_url='https://opengameart.org/a.wav',indexed_sha256='same-content')
        second=dict(first,id='unique-hash-b',download_url='https://opengameart.org/b.wav')
        self.assertEqual(merge_assets(self.lib,[first,second]),1)

if __name__=='__main__':unittest.main()
