import unittest
import os

class TestLandingJs(unittest.TestCase):
    def test_landing_page_exists(self):
        self.assertTrue(os.path.exists('landing-page/app.js'), "landing-page/app.js does not exist")

    def test_init_landing_app(self):
        with open('landing-page/app.js', 'r') as file:
            content = file.read()
        self.assertTrue('initLandingApp' in content)

    def test_dom_content_loaded(self):
        with open('landing-page/app.js', 'r') as file:
            content = file.read()
        self.assertTrue('DOMContentLoaded' in content)

    def test_start_fleet_simulation(self):
        with open('landing-page/app.js', 'r') as file:
            content = file.read()
        self.assertTrue('startFleetSimulation' in content)

    def test_reset_simulation(self):
        with open('landing-page/app.js', 'r') as file:
            content = file.read()
        self.assertTrue('resetSimulation' in content)

    def test_append_log_entry(self):
        with open('landing-page/app.js', 'r') as file:
            content = file.read()
        self.assertTrue('appendLogEntry' in content)

    def test_bind_buttons(self):
        with open('landing-page/app.js', 'r') as file:
            content = file.read()
        self.assertTrue('#btnStartSim' in content and '#btnResetSim' in content)

if __name__ == '__main__':
    unittest.main()
