import unittest
import os

class TestLandingPage(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(os.path.exists('landing-page/index.html'), "The file 'landing-page/index.html' does not exist.")

    def test_doctype(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('<!DOCTYPE html>', content, "The file does not contain the <!DOCTYPE html> declaration.")

    def test_title(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('<title>Agent Cockpit</title>', content, "The file does not contain the <title>Agent Cockpit</title> tag.")

    def test_meta_viewport(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1.0">', content, "The file does not contain the <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"> tag.")

    def test_stylesheet_link(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('<link rel="stylesheet" href="styles.css">', content, "The file does not contain the <link rel=\"stylesheet\" href=\"styles.css\"> tag.")

    def test_script_tag(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('<script src="app.js"></script>', content, "The file does not contain the <script src=\"app.js\"></script> tag.")

    def test_site_header(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('site-header', content, "The file does not contain the .site-header class.")
            self.assertIn('brand', content, "The file does not contain the .brand class.")
            self.assertIn('badge-version', content, "The file does not contain the .badge-version class.")

    def test_hero_section(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('hero-section', content, "The file does not contain the .hero-section class.")
            self.assertIn('hero-title', content, "The file does not contain the .hero-title class.")
            self.assertIn('hero-subtitle', content, "The file does not contain the .hero-subtitle class.")
            self.assertIn('stats-grid', content, "The file does not contain the .stats-grid class.")

    def test_architecture_section(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('architecture-section', content, "The file does not contain the .architecture-section class.")
            self.assertIn('fleet-grid', content, "The file does not contain the .fleet-grid class.")
            self.assertIn('agent-pair-card', content, "The file does not contain the .agent-pair-card class.")

    def test_simulator_section(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('simulator-section', content, "The file does not contain the .simulator-section class.")
            self.assertIn('terminal-window', content, "The file does not contain the .terminal-window class.")
            self.assertIn('log-stream', content, "The file does not contain the .log-stream class.")

    def test_hardware_section(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('hardware-section', content, "The file does not contain the .hardware-section class.")
            self.assertIn('matrix-table', content, "The file does not contain the .matrix-table class.")

    def test_site_footer(self):
        with open('landing-page/index.html', 'r') as file:
            content = file.read()
            self.assertIn('site-footer', content, "The file does not contain the .site-footer class.")

if __name__ == '__main__':
    unittest.main()
