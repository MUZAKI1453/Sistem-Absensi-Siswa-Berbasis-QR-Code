import os
# V Hapus 'datetime' dan 'exc' dari import
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    jsonify, flash
)
from models import (
    db
    # V Hapus model-model pengaturan dari sini
    # SettingWaktu, SettingWaktuGuruStaf,
    # SettingWaktuKeamanan, HariLibur
)
from absensi_pegawai_routes import absensi_pegawai_bp
from absensi_routes import absensi_bp, get_badge_color
from dashboard_routes import dashboard_bp
from export_routes import export_bp
from jadwal_keamanan_routes import jadwal_keamanan_bp
from kelola_kelas_routes import kelola_kelas_bp
from notifikasi_terlambat import start_scheduler
from pegawai_routes import pegawai_bp
from scan_routes import scan_bp
from siswa_routes import siswa_bp
from izin_routes import izin_bp
from izin_admin_routes import izin_admin_bp

# =======================================================================
#  V TAMBAHKAN IMPORT BLUEPRINT BARU
# =======================================================================
from pengaturan_routes import pengaturan_bp


# =======================================================================
#  INISIALISASI APLIKASI FLASK
# =======================================================================
# Muat environment variables dari file .env
load_dotenv()

app = Flask(__name__)
app.secret_key = "absensi_qr_secret"

# ==============================================================================
#  KONFIGURASI DATABASE DARI ENVIRONMENT VARIABLES (.env)
# ==============================================================================
# Ambil konfigurasi dari environment variables
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
HOST = os.getenv("DB_HOST")
DATABASE_NAME = os.getenv("DB_NAME")

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+mysqlconnector://{USER}:{PASSWORD}@{HOST}/{DATABASE_NAME}'
# ==============================================================================

# Folder utama untuk QR
BASE_QR_FOLDER = os.path.join('static', 'qr_codes')

# Folder khusus siswa dan pegawai
app.config['QR_FOLDER_SISWA'] = os.path.join(BASE_QR_FOLDER, 'siswa')
app.config['QR_FOLDER_PEGAWAI'] = os.path.join(BASE_QR_FOLDER, 'pegawai')

# Inisialisasi database
db.init_app(app)
with app.app_context():
    db.create_all()
    os.makedirs(app.config['QR_FOLDER_SISWA'], exist_ok=True)
    os.makedirs(app.config['QR_FOLDER_PEGAWAI'], exist_ok=True)

app.register_blueprint(dashboard_bp)
app.register_blueprint(export_bp)
app.register_blueprint(absensi_bp)
app.jinja_env.filters['get_badge_color'] = get_badge_color
app.register_blueprint(kelola_kelas_bp)
app.register_blueprint(scan_bp)
app.register_blueprint(jadwal_keamanan_bp)
app.register_blueprint(absensi_pegawai_bp)
app.register_blueprint(siswa_bp)
app.register_blueprint(pegawai_bp)
app.register_blueprint(izin_bp)
app.register_blueprint(izin_admin_bp)

# =======================================================================
#  V DAFTARKAN BLUEPRINT BARU
# =======================================================================
app.register_blueprint(pengaturan_bp)


# =======================================================================
#  FUNGSI HELPER & UTILITAS (TIDAK BERUBAH)
# =======================================================================
def check_admin_session():
    """Periksa sesi admin, redirect ke login jika belum login."""
    return redirect(url_for("login")) if "admin" not in session else None


def get_badge_color(status):
    """Tentukan warna badge berdasarkan status untuk filter Jinja2."""
    return 'success' if status in ['Hadir',
                                   'Terlambat'] else 'warning text-dark' if status == 'Izin' else 'info text-dark' if status == 'Sakit' else 'danger'


app.jinja_env.filters['get_badge_color'] = get_badge_color


# =======================================================================
#  ROUTE: AUTENTIKASI ADMIN (TIDAK BERUBAH)
# =======================================================================
@app.route("/", methods=["GET", "POST"])
def login():
    """Rute login admin."""
    if request.method == "POST":
        # Ambil kredensial admin dari environment variables
        ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
        ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123")

        if request.form["username"] == ADMIN_USERNAME and request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("dashboard_bp.dashboard"))

        flash("Username atau password salah.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Rute logout, hapus sesi admin."""
    session.clear()
    flash("Anda telah logout.", "success")
    return redirect(url_for("login"))


# =======================================================================
#  V SEMUA FUNGSI PENGATURAN DIHAPUS DARI SINI
# =======================================================================
# @app.route("/pengaturan", ...)
# @app.route("/hari_libur", ...)
# @app.route("/api/setting_siswa", ...)
# @app.route("/pengaturan_pegawai", ...)
# =======================================================================


# =======================================================================
#  MAIN EXECUTION
# =======================================================================
if __name__ == "__main__":
    with app.app_context():
        start_scheduler(app)
    app.run(debug=False, host="0.0.0.0", port=8080)