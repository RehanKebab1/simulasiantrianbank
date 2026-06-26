import time
import random
import threading
import sys
import select
from datetime import datetime
from queue import PriorityQueue

# Deteksi platform untuk input non-blocking
try:
    import tty
    import termios
    _UNIX = True
except ImportError:
    import msvcrt
    _UNIX = False


# ===========================================================
# FUNGSI INPUT NON-BLOCKING
# ===========================================================

def _baca_unix(prompt, refresh_event):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    pengaturan_lama = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        buffer = ""
        while True:
            siap, _, _ = select.select([sys.stdin], [], [], 0.1)
            if siap:
                karakter = sys.stdin.read(1)
                if karakter in ('\r', '\n'):
                    sys.stdout.write('\r\n')
                    sys.stdout.flush()
                    return buffer
                elif karakter in ('\x7f', '\b'):
                    if buffer:
                        buffer = buffer[:-1]
                        sys.stdout.write('\b \b')
                        sys.stdout.flush()
                elif karakter == '\x03':
                    raise KeyboardInterrupt
                elif karakter == '\x04':
                    raise EOFError
                else:
                    buffer += karakter
                    sys.stdout.write(karakter)
                    sys.stdout.flush()

            if refresh_event.is_set():
                sys.stdout.write('\r\n')
                sys.stdout.flush()
                return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, pengaturan_lama)

def _baca_windows(prompt, refresh_event):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    buffer = ""
    while True:
        if msvcrt.kbhit():
            karakter = msvcrt.getwch()
            if karakter in ('\r', '\n'):
                sys.stdout.write('\n')
                sys.stdout.flush()
                return buffer
            elif karakter == '\x08':
                if buffer:
                    buffer = buffer[:-1]
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
            elif karakter == '\x03':
                raise KeyboardInterrupt
            else:
                buffer += karakter
                sys.stdout.write(karakter)
                sys.stdout.flush()
        if refresh_event.is_set():
            sys.stdout.write('\n')
            sys.stdout.flush()
            return None
        time.sleep(0.05)

def baca_input(prompt, refresh_event):
    if _UNIX:
        return _baca_unix(prompt, refresh_event)
    else:
        return _baca_windows(prompt, refresh_event)


# ===========================================================
# KELAS NASABAH
# ===========================================================

class Nasabah:
    def __init__(self, nama, nomor_antrian, prioritas=2):
        self.nama = nama
        self.prioritas = prioritas
        self.nomor_antrian = nomor_antrian
        self.waktu_datang = datetime.now()

    def __lt__(self, other):
        # Jika prioritasnya BEDA, urutkan berdasarkan prioritas (0 menang lawan 2)
        if self.prioritas != other.prioritas:
            return self.prioritas < other.prioritas
        
        # Jika prioritasnya SAMA, urutkan berdasarkan waktu datang (FIFO)
        return self.waktu_datang < other.waktu_datang

    def __str__(self):
        jenis = {0: "VIP", 1: "Lansia", 2: "Reguler"}
        return f"[{jenis[self.prioritas]}] {self.nama} (Antrian:{self.nomor_antrian})"


# ===========================================================
# KELAS TELLER
# ===========================================================

class Teller:
    def __init__(self, id_teller):
        self.id = id_teller
        self.status = "KOSONG"
        self.nasabah_dilayani = None
        self._lock = threading.Lock()

    def layani(self, nasabah, callback_selesai=None):
        def _proses():
            with self._lock:
                self.status = "SIBUK"
                self.nasabah_dilayani = nasabah

            durasi = random.randint(2, 5)
            print(f"\n   🟢 Teller-{self.id} mulai melayani {nasabah}... "
                  f"(Estimasi: {durasi} detik)")

            time.sleep(durasi)

            with self._lock:
                self.status = "KOSONG"
                self.nasabah_dilayani = None

            print(f"   🔴 Teller-{self.id} selesai melayani {nasabah}.\n")

            if callback_selesai:
                callback_selesai(nasabah, durasi)

        thread = threading.Thread(target=_proses, daemon=True)
        thread.start()
        return thread


# ===========================================================
# KELAS SISTEM BANK
# ===========================================================

class SistemBank:
    def __init__(self, jumlah_teller=4):
        self.antrian_nasabah = PriorityQueue()
        self.daftar_teller = [Teller(i + 1) for i in range(jumlah_teller)]
        self.statistik = {
            "total_nasabah": 0,
            "terlayani": 0,
            "total_waktu_tunggu": 0
        }
        self._statistik_lock = threading.Lock()
        self.nama_file_log = "log_bank.txt"

    def log_kegiatan(self, pesan):
        waktu = datetime.now().strftime("%H:%M:%S")
        teks = f"[{waktu}] {pesan}\n"
        print(teks.strip())
        
        with open(self.nama_file_log, "a") as file_log:
            file_log.write(teks)

    def nasabah_datang(self, nama, prioritas=2):
        with self._statistik_lock:
            self.statistik["total_nasabah"] += 1
            nomor_antrian_baru = self.statistik["total_nasabah"]
            
        nasabah_baru = Nasabah(nama, nomor_antrian_baru, prioritas)
        self.antrian_nasabah.put(nasabah_baru)
        self.log_kegiatan(f"Nasabah {nasabah_baru} masuk antrian.")

    def proses_antrian(self, id_teller_spesifik=None):
        if id_teller_spesifik:
            teller_kosong = [t for t in self.daftar_teller if t.id == id_teller_spesifik and t.status == "KOSONG"]
        else:
            teller_kosong = [t for t in self.daftar_teller if t.status == "KOSONG"]

        if not teller_kosong:
            if not id_teller_spesifik:
                self.log_kegiatan("Semua teller sedang sibuk.")
            return

        if self.antrian_nasabah.empty():
            if not id_teller_spesifik:
                self.log_kegiatan("Antrian kosong, tidak ada yang diproses.")
            return

        nasabah = self.antrian_nasabah.get()
        waktu_tunggu = (datetime.now() - nasabah.waktu_datang).total_seconds()
        teller_pilih = teller_kosong[0]
        id_teller = teller_pilih.id

        def selesai(n, durasi):
            with self._statistik_lock:
                self.statistik["total_waktu_tunggu"] += waktu_tunggu
                self.statistik["terlayani"] += 1
            self.log_kegiatan(
                f"{n} selesai dilayani Teller-{id_teller}. "
                f"Waktu tunggu: {waktu_tunggu:.2f} dtk. Durasi: {durasi} dtk."
            )
            # Otomatis panggil nasabah berikutnya
            threading.Thread(target=self.proses_antrian, args=(id_teller,), daemon=True).start()

        teller_pilih.layani(nasabah, callback_selesai=selesai)
        self.log_kegiatan(f"{nasabah} mulai dilayani Teller-{id_teller}.")

    def ada_teller_sibuk(self):
        return any(t.status == "SIBUK" for t in self.daftar_teller)

    def tampilkan_status(self):
        print("\n--- STATUS REAL-TIME ---")
        for t in self.daftar_teller:
            if t.status == "SIBUK":
                info = f"(Melayani: {t.nasabah_dilayani})"
            else:
                info = ""
            print(f"  Teller-{t.id}: [{t.status}] {info}")
        print(f"  Sisa Antrian : {self.antrian_nasabah.qsize()} orang")
        print("------------------------\n")

    def tampilkan_laporan_akhir(self):
        for t in self.daftar_teller:
            while t.status == "SIBUK":
                time.sleep(0.5)

        with self._statistik_lock:
            avg_wait = (
                self.statistik["total_waktu_tunggu"] / self.statistik["terlayani"]
                if self.statistik["terlayani"] > 0 else 0
            )
            print("\n========================================")
            print("       LAPORAN AKHIR SIMULASI           ")
            print("========================================")
            print(f"  Total Nasabah Datang   : {self.statistik['total_nasabah']}")
            print(f"  Total Nasabah Terlayani: {self.statistik['terlayani']}")
            print(f"  Rata-rata Waktu Tunggu : {avg_wait:.2f} detik")
            print("========================================\n")


# ===========================================================
# MANAJER MENU
# ===========================================================

class ManajerMenu:
    def __init__(self, bank: SistemBank):
        self.bank = bank
        self._refresh_event = threading.Event()
        self._stop = threading.Event()
        self._status_monitor = False

    def _monitor(self):
        while not self._stop.is_set():
            time.sleep(0.3)
            status_sekarang = self.bank.ada_teller_sibuk()
            if status_sekarang != self._status_monitor:
                self._status_monitor = status_sekarang
                time.sleep(0.2)
                self._refresh_event.set()

    def _cetak_menu(self):
        print("\n" + "=" * 45)
        if self.bank.ada_teller_sibuk():
            print("  ⏳ TELLER SEDANG BEKERJA...")
            print("=" * 45)
            print("  MENU:")
            print("  1. Lihat Status Bank")
            print("  2. Keluar & Lihat Laporan")
            print("=" * 45)
            return "Pilih Menu (1-2): ", True
        else:
            print("  MENU:")
            print("=" * 45)
            print("  1. Lihat Status Bank")
            print("  2. Nasabah Reguler Datang")
            print("  3. Nasabah VIP Datang")
            print("  4. Nasabah Lansia Datang")
            print("  5. Nasabah VIP & Reguler Datang (Simulasi Bareng)")
            print("  6. Proses Antrian (Jalankan Teller)")
            print("  7. Keluar & Lihat Laporan")
            print("=" * 45)
            # Karena menunya nambah, kita ubah batas pilihannya jadi 1-7
            return "Pilih Menu (1-7): ", False 

    def jalankan(self):
        t_monitor = threading.Thread(target=self._monitor, daemon=True)
        t_monitor.start()

        lanjut = True
        while lanjut:
            prompt, mode_sibuk = self._cetak_menu()
            self._refresh_event.clear()

            pilihan = baca_input(prompt, self._refresh_event)

            if pilihan is None:
                continue

            pilihan = pilihan.strip()

            if mode_sibuk:
                lanjut = self._handle_sibuk(pilihan)
            else:
                lanjut = self._handle_normal(pilihan)

        self._stop.set()

    def _handle_sibuk(self, pilihan):
        if pilihan == '1':
            self.bank.tampilkan_status()
        elif pilihan == '2':
            return False
        else:
            print("❌ Pilihan tidak valid!")
        return True

    def _minta_nama(self, prompt_text):
        try:
            nama = input(prompt_text).strip()
            return nama
        except (KeyboardInterrupt, EOFError):
            print("\n❌ Input dibatalkan.")
            return ""

    def _handle_normal(self, pilihan):
        if pilihan == '1':
            self.bank.tampilkan_status()
        elif pilihan == '2':
            nama = self._minta_nama("Nama Nasabah Reguler: ")
            if nama: self.bank.nasabah_datang(nama, prioritas=2)
        elif pilihan == '3':
            nama = self._minta_nama("Nama Nasabah VIP: ")
            if nama: self.bank.nasabah_datang(nama, prioritas=0)
        elif pilihan == '4':
            nama = self._minta_nama("Nama Nasabah Lansia: ")
            if nama: self.bank.nasabah_datang(nama, prioritas=1)
        elif pilihan == '5':
            # FITUR BARU: Input dua nasabah berbarengan
            print("\n--- Simulasi Kedatangan Berbarengan ---")
            nama_reguler = self._minta_nama("Masukkan Nama Nasabah Reguler: ")
            nama_vip = self._minta_nama("Masukkan Nama Nasabah VIP    : ")
            if nama_reguler and nama_vip:
                # Memasukkan ke antrian. VIP akan otomatis disortir ke depan
                self.bank.nasabah_datang(nama_reguler, prioritas=2)
                self.bank.nasabah_datang(nama_vip, prioritas=0)
                print("✅ Keduanya berhasil masuk antrean.")
        elif pilihan == '6':
            print("\n⏳ Memproses antrian...")
            for _ in range(len(self.bank.daftar_teller)):
                self.bank.proses_antrian()
            time.sleep(0.05)
            self._status_monitor = self.bank.ada_teller_sibuk()
        elif pilihan == '7':
            return False
        else:
            print("❌ Pilihan tidak valid!")
        return True


# ===========================================================
# MAIN
# ===========================================================

if __name__ == "__main__":
    print("\n🏦 SIMULASI ANTRIAN BANK REALISTIS (PBL STRUKTUR DATA)")
    print("-----------------------------------------------------")

    bank = SistemBank(jumlah_teller=4)
    menu = ManajerMenu(bank)

    try:
        menu.jalankan()
    except KeyboardInterrupt:
        print("\n\nMematikan sistem secara paksa...")
    finally:
        bank.tampilkan_laporan_akhir()