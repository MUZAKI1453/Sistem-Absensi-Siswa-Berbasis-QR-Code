from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from models import SettingWaktu
from utils import kirim_notifikasi_terlambat

scheduler = None  # simpan di global supaya tidak dihapus garbage collector


def start_scheduler(app):
    """
    Menjadwalkan pengiriman notifikasi keterlambatan
    secara otomatis berdasarkan jam batas terlambat dari SettingWaktu.
    """
    global scheduler
    scheduler = BackgroundScheduler()

    with app.app_context():
        setting = SettingWaktu.query.first()
        if not setting or not setting.jam_terlambat_selesai:
            print("⚠️ Jam batas terlambat belum diatur di menu Pengaturan.")
            return

        waktu_batas = datetime.combine(datetime.now().date(), setting.jam_terlambat_selesai)
        waktu_jadwal = waktu_batas + timedelta(minutes=1)

        # Jika sudah lewat hari ini, jadwalkan untuk besok
        if waktu_jadwal < datetime.now():
            waktu_jadwal = waktu_jadwal + timedelta(days=1)
            print("⏩ Waktu sudah lewat, notifikasi dijadwalkan untuk BESOK.")

        print(f"📆 Notifikasi akan dikirim otomatis pada {waktu_jadwal.strftime('%H:%M:%S')} ({waktu_jadwal.date()}).")

        scheduler.add_job(
            func=lambda: kirim_notifikasi_terlambat(app),
            trigger='date',
            run_date=waktu_jadwal,
            id='notif_terlambat',
            replace_existing=True
        )

        scheduler.start()
        print("✅ Scheduler notifikasi terlambat AKTIF.")


def stop_scheduler():
    """Berhentiin scheduler jika dibutuhkan"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        print("🛑 Scheduler dimatikan.")