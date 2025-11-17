from telegram_scraper import ScraperGUI, QApplication
import sys
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScraperGUI()
    window.show()
    sys.exit(app.exec())