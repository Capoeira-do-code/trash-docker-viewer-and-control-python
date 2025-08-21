# main.py
import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Helo Wrlod")

    # Iniciamos ventana principal
    window = MainWindow()
    window.setWindowTitle("Helo Wrlod - Docker SSH Manager") 
    window.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
