# install.py
import subprocess
import sys

def install_packages():
    """Liest requirements.txt und installiert die Pakete mit pip."""
    try:
        print("Installiere notwendige Pakete...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("\nInstallation erfolgreich abgeschlossen!")
        print("Sie können jetzt das Hauptprogramm starten mit: python3 dividendenrendite_tracker.py")
    except subprocess.CalledProcessError as e:
        print(f"\nFehler bei der Installation der Pakete: {e}")
        print("Stellen Sie sicher, dass 'pip' und Python 3 korrekt installiert sind.")
    except FileNotFoundError:
        print("\nFehler: Die Datei 'requirements.txt' wurde nicht im selben Ordner gefunden.")
        print("Bitte stellen Sie sicher, dass beide Dateien im selben Verzeichnis liegen.")

if __name__ == "__main__":
    install_packages()
