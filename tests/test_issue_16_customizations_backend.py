import os
import sys
import json
import shutil
import tempfile
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server.customizations_manager import CustomizationsManager
from server.opencode_manager import sync_opencode_config, sync_customizations_to_opencode


class TestCustomizationsManagerInitialization(unittest.TestCase):
    """Testa a inicialização determinística e diretórios canônicos do CustomizationsManager."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='cockpit_customizations_test_')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_init_with_explicit_dir(self):
        manager = CustomizationsManager(base_dir=self.test_dir)
        self.assertEqual(manager.base_dir, self.test_dir)
        self.assertTrue(os.path.isdir(os.path.join(self.test_dir, 'mcp')))
        self.assertTrue(os.path.isdir(os.path.join(self.test_dir, 'skills')))

    def test_init_with_env_var(self):
        custom_env_dir = os.path.join(self.test_dir, 'env_customizations')
        old_env = os.environ.get('COCKPIT_CUSTOMIZATIONS_DIR')
        os.environ['COCKPIT_CUSTOMIZATIONS_DIR'] = custom_env_dir
        try:
            manager = CustomizationsManager()
            self.assertEqual(manager.base_dir, custom_env_dir)
            self.assertTrue(os.path.isdir(os.path.join(custom_env_dir, 'mcp')))
            self.assertTrue(os.path.isdir(os.path.join(custom_env_dir, 'skills')))
        finally:
            if old_env is not None:
                os.environ['COCKPIT_CUSTOMIZATIONS_DIR'] = old_env
            else:
                os.environ.pop('COCKPIT_CUSTOMIZATIONS_DIR', None)

    def test_canonical_default_path(self):
        old_env = os.environ.pop('COCKPIT_CUSTOMIZATIONS_DIR', None)
        try:
            manager = CustomizationsManager()
            expected_canonical = os.path.expanduser('~/.config/agent-cockpit/customizations')
            self.assertEqual(manager.base_dir, expected_canonical)
        finally:
            if old_env is not None:
                os.environ['COCKPIT_CUSTOMIZATIONS_DIR'] = old_env


class TestCustomizationsManagerMCPCrud(unittest.TestCase):
    """Testa operações CRUD completas para Servidores MCP (stdio e sse/http)."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='cockpit_mcp_test_')
        self.manager = CustomizationsManager(base_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_create_and_get_stdio_mcp(self):
        mcp_data = {
            'name': 'filesystem-server',
            'type': 'stdio',
            'command': 'npx',
            'args': ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
            'env': {'DEBUG': 'true'},
            'enabled': True,
            'description': 'Local filesystem access'
        }
        created = self.manager.create_mcp(mcp_data)
        self.assertIn('id', created)
        self.assertEqual(created['name'], 'filesystem-server')
        self.assertEqual(created['type'], 'stdio')
        self.assertEqual(created['command'], 'npx')
        self.assertEqual(created['args'], ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'])
        self.assertEqual(created['env'], {'DEBUG': 'true'})
        self.assertTrue(created['enabled'])

        mcp_file = os.path.join(self.test_dir, 'mcp', f"{created['id']}.json")
        self.assertTrue(os.path.isfile(mcp_file))

        retrieved = self.manager.get_mcp(created['id'])
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['id'], created['id'])
        self.assertEqual(retrieved['command'], 'npx')

    def test_create_and_get_sse_mcp(self):
        mcp_data = {
            'name': 'remote-analytics',
            'type': 'sse',
            'url': 'http://localhost:8080/sse',
            'headers': {'Authorization': 'Bearer token123'},
            'enabled': True
        }
        created = self.manager.create_mcp(mcp_data)
        self.assertEqual(created['type'], 'sse')
        self.assertEqual(created['url'], 'http://localhost:8080/sse')

        retrieved = self.manager.get_mcp(created['id'])
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['url'], 'http://localhost:8080/sse')

    def test_validation_mcp(self):
        with self.assertRaises(ValueError):
            self.manager.create_mcp({'type': 'stdio', 'command': 'echo'})

        with self.assertRaises(ValueError):
            self.manager.create_mcp({'name': 'bad', 'type': 'unknown'})

        with self.assertRaises(ValueError):
            self.manager.create_mcp({'name': 'bad_stdio', 'type': 'stdio'})

        with self.assertRaises(ValueError):
            self.manager.create_mcp({'name': 'bad_sse', 'type': 'sse'})

    def test_list_mcps(self):
        self.manager.create_mcp({'name': 'mcp-1', 'type': 'stdio', 'command': 'python3'})
        self.manager.create_mcp({'name': 'mcp-2', 'type': 'sse', 'url': 'https://mcp.example.com/sse'})

        mcps = self.manager.list_mcps()
        self.assertEqual(len(mcps), 2)
        names = [m['name'] for m in mcps]
        self.assertIn('mcp-1', names)
        self.assertIn('mcp-2', names)

    def test_update_mcp(self):
        created = self.manager.create_mcp({
            'name': 'updatable-mcp',
            'type': 'stdio',
            'command': 'node',
            'args': ['index.js']
        })
        mcp_id = created['id']

        updated = self.manager.update_mcp(mcp_id, {
            'name': 'renamed-mcp',
            'command': 'bun',
            'args': ['run', 'index.ts']
        })
        self.assertEqual(updated['id'], mcp_id)
        self.assertEqual(updated['name'], 'renamed-mcp')
        self.assertEqual(updated['command'], 'bun')
        self.assertEqual(updated['args'], ['run', 'index.ts'])

        refetched = self.manager.get_mcp(mcp_id)
        self.assertEqual(refetched['name'], 'renamed-mcp')
        self.assertEqual(refetched['command'], 'bun')

    def test_delete_mcp(self):
        created = self.manager.create_mcp({
            'name': 'to-delete',
            'type': 'stdio',
            'command': 'echo'
        })
        mcp_id = created['id']
        self.assertTrue(self.manager.delete_mcp(mcp_id))
        self.assertIsNone(self.manager.get_mcp(mcp_id))
        self.assertFalse(self.manager.delete_mcp(mcp_id))

    def test_toggle_mcp(self):
        created = self.manager.create_mcp({
            'name': 'toggle-me',
            'type': 'stdio',
            'command': 'echo',
            'enabled': True
        })
        mcp_id = created['id']

        toggled = self.manager.toggle_mcp(mcp_id)
        self.assertFalse(toggled['enabled'])

        toggled = self.manager.toggle_mcp(mcp_id)
        self.assertTrue(toggled['enabled'])

        toggled = self.manager.toggle_mcp(mcp_id, enabled=False)
        self.assertFalse(toggled['enabled'])


class TestCustomizationsManagerSkillsCrud(unittest.TestCase):
    """Testa operações CRUD completas para Skills (pastas e SKILL.md)."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='cockpit_skills_test_')
        self.manager = CustomizationsManager(base_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    def test_create_and_get_skill(self):
        instructions_text = """# TDD Guidelines
Always write failing test first.
Verify red then green."""
        skill_data = {
            'name': 'test-driven-development',
            'description': 'Enforce TDD rules across all coding tasks',
            'instructions': instructions_text,
            'enabled': True
        }
        created = self.manager.create_skill(skill_data)
        self.assertEqual(created['name'], 'test-driven-development')
        self.assertEqual(created['description'], 'Enforce TDD rules across all coding tasks')
        self.assertTrue(created['enabled'])
        self.assertIn('Always write failing test first', created['instructions'])

        skill_dir = os.path.join(self.test_dir, 'skills', 'test-driven-development')
        skill_file = os.path.join(skill_dir, 'SKILL.md')
        self.assertTrue(os.path.isdir(skill_dir))
        self.assertTrue(os.path.isfile(skill_file))

        with open(skill_file, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertTrue(content.startswith('---'))
        self.assertIn('name: test-driven-development', content)
        self.assertIn('description: Enforce TDD rules across all coding tasks', content)

        retrieved = self.manager.get_skill('test-driven-development')
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['name'], 'test-driven-development')
        self.assertEqual(retrieved['instructions'], created['instructions'])

    def test_list_skills(self):
        self.manager.create_skill({
            'name': 'skill-alpha',
            'description': 'Alpha skill',
            'instructions': 'Alpha rules'
        })
        self.manager.create_skill({
            'name': 'skill-beta',
            'description': 'Beta skill',
            'instructions': 'Beta rules'
        })

        skills = self.manager.list_skills()
        self.assertEqual(len(skills), 2)
        names = [s['name'] for s in skills]
        self.assertIn('skill-alpha', names)
        self.assertIn('skill-beta', names)

    def test_update_skill(self):
        self.manager.create_skill({
            'name': 'code-review',
            'description': 'Perform review',
            'instructions': 'Check code'
        })

        updated = self.manager.update_skill('code-review', {
            'description': 'Comprehensive Code Review',
            'instructions': 'Deeply inspect architecture, tests, and security'
        })
        self.assertEqual(updated['description'], 'Comprehensive Code Review')
        self.assertIn('Deeply inspect architecture', updated['instructions'])

        retrieved = self.manager.get_skill('code-review')
        self.assertEqual(retrieved['description'], 'Comprehensive Code Review')

    def test_delete_skill(self):
        self.manager.create_skill({
            'name': 'temp-skill',
            'description': 'To be removed',
            'instructions': 'Temporary'
        })
        skill_dir = os.path.join(self.test_dir, 'skills', 'temp-skill')
        self.assertTrue(os.path.isdir(skill_dir))

        self.assertTrue(self.manager.delete_skill('temp-skill'))
        self.assertFalse(os.path.exists(skill_dir))
        self.assertIsNone(self.manager.get_skill('temp-skill'))
        self.assertFalse(self.manager.delete_skill('temp-skill'))

    def test_toggle_skill(self):
        self.manager.create_skill({
            'name': 'toggleable-skill',
            'description': 'Skill for toggle test',
            'instructions': 'Do something',
            'enabled': True
        })

        toggled = self.manager.toggle_skill('toggleable-skill')
        self.assertFalse(toggled['enabled'])

        retrieved = self.manager.get_skill('toggleable-skill')
        self.assertFalse(retrieved['enabled'])

        toggled = self.manager.toggle_skill('toggleable-skill', enabled=True)
        self.assertTrue(toggled['enabled'])


class TestCustomizationsOpenCodeSync(unittest.TestCase):
    """Testa sincronização segura de MCPs ativos com o opencode.json sem corromper conectores."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='cockpit_opencode_sync_test_')
        self.manager = CustomizationsManager(base_dir=os.path.join(self.test_dir, 'customizations'))
        self.opencode_path = os.path.join(self.test_dir, 'opencode.json')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_sync_with_opencode_preserves_existing_data(self):
        initial_opencode = {
            '': 'https://opencode.ai/config.json',
            'model': 'omniroute/claude-3-7-sonnet',
            'provider': {
                'omniroute': {
                    'npm': '@ai-sdk/openai',
                    'options': {'baseURL': 'http://localhost:20128/v1', 'apiKey': 'test-key'}
                }
            },
            'mcp': {
                'agent-cockpit': {
                    'type': 'local',
                    'command': ['python3', '/path/to/mcp_server.py'],
                    'enabled': True
                }
            }
        }
        with open(self.opencode_path, 'w', encoding='utf-8') as f:
            json.dump(initial_opencode, f, indent=2)

        self.manager.create_mcp({
            'name': 'sqlite-custom',
            'type': 'stdio',
            'command': 'uvx',
            'args': ['mcp-server-sqlite', '--db-path', '/test.db'],
            'env': {'SQLITE_TIMEOUT': '5000'},
            'enabled': True
        })
        self.manager.create_mcp({
            'name': 'disabled-mcp',
            'type': 'stdio',
            'command': 'echo',
            'enabled': False
        })
        self.manager.create_mcp({
            'name': 'cloud-mcp',
            'type': 'sse',
            'url': 'https://mcp.cloud.provider/events',
            'enabled': True
        })

        result = self.manager.sync_with_opencode(self.opencode_path)
        self.assertEqual(result.get('status'), 'success')

        with open(self.opencode_path, 'r', encoding='utf-8') as f:
            updated_opencode = json.load(f)

        self.assertEqual(updated_opencode['model'], 'omniroute/claude-3-7-sonnet')
        self.assertIn('omniroute', updated_opencode['provider'])
        self.assertIn('agent-cockpit', updated_opencode['mcp'])
        self.assertEqual(updated_opencode['mcp']['agent-cockpit']['type'], 'local')

        self.assertIn('sqlite-custom', updated_opencode['mcp'])
        sqlite_cfg = updated_opencode['mcp']['sqlite-custom']
        self.assertEqual(sqlite_cfg['type'], 'local')
        self.assertEqual(sqlite_cfg['command'], ['uvx', 'mcp-server-sqlite', '--db-path', '/test.db'])
        self.assertEqual(sqlite_cfg.get('environment', {}).get('SQLITE_TIMEOUT'), '5000')

        self.assertIn('cloud-mcp', updated_opencode['mcp'])
        cloud_cfg = updated_opencode['mcp']['cloud-mcp']
        self.assertEqual(cloud_cfg['type'], 'remote')
        self.assertEqual(cloud_cfg['url'], 'https://mcp.cloud.provider/events')

        self.assertNotIn('disabled-mcp', updated_opencode['mcp'])

    def test_sync_hook_in_opencode_manager(self):
        initial_opencode = {
            'mcp': {
                'agent-cockpit': {'type': 'local', 'command': ['python3', 'mcp.py']}
            }
        }
        with open(self.opencode_path, 'w', encoding='utf-8') as f:
            json.dump(initial_opencode, f, indent=2)

        self.manager.create_mcp({
            'name': 'auto-hooked-mcp',
            'type': 'stdio',
            'command': 'node',
            'args': ['server.js'],
            'enabled': True
        })

        res = sync_customizations_to_opencode(
            opencode_path=self.opencode_path,
            customizations_dir=self.manager.base_dir
        )
        self.assertEqual(res['status'], 'success')

        with open(self.opencode_path, 'r', encoding='utf-8') as f:
            synced = json.load(f)

        self.assertIn('agent-cockpit', synced['mcp'])
        self.assertIn('auto-hooked-mcp', synced['mcp'])


if __name__ == '__main__':
    unittest.main()
