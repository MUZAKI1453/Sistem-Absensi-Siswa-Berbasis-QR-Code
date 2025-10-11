import csv, os, io
import json
import calendar as cal
from datetime import datetime, time, date

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    send_file, jsonify, send_from_directory, flash, Response
)
from PIL import Image, ImageDraw, ImageFont
import pandas as pd, qrcode, requests
from sqlalchemy import and_, select, delete

from models import (
    db, Siswa, Absensi, SettingWaktu, Kelas,
    Pegawai, AbsensiPegawai, SettingWaktuGuruStaf,
    SettingWaktuKeamanan, JadwalKeamanan
)
from export_routes import export_bp
from absensi_routes import absensi_bp, get_badge_color
from dashboard_routes import dashboard_bp
from kelola_kelas_routes import kelola_kelas_bp
from scan_routes import scan_bp
from jadwal_keamanan_routes import jadwal_keamanan_bp
from absensi_pegawai_routes import absensi_pegawai_bp
from siswa_routes import siswa_bp
from pegawai_routes import pegawai_bp

# =======================================================================
#  INISIALISASI APLIKASI FLASK
# =======================================================================
app = Flask(__name__)
app.secret_key = "absensi_qr_secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///absensi.db'

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

# =======================================================================
#  FUNGSI HELPER & UTILITAS
# =======================================================================
def check_admin_session():
    """Periksa sesi admin, redirect ke login jika belum login."""
    return redirect(url_for("login")) if "admin" not in session else None

def get_badge_color(status):
    """Tentukan warna badge berdasarkan status untuk filter Jinja2."""
    return 'success' if status in ['Hadir', 'Terlambat'] else 'warning text-dark' if status == 'Izin' else 'info text-dark' if status == 'Sakit' else 'danger'
app.jinja_env.filters['get_badge_color'] = get_badge_color

# =======================================================================
#  ROUTE: AUTENTIKASI ADMIN
# =======================================================================
@app.route("/", methods=["GET", "POST"])
def login():
    """Rute login admin (gunakan autentikasi aman di produksi)."""
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "123":
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
#  ROUTE: PENGATURAN UMUM (GET / POST)
# =======================================================================
@app.route("/pengaturan", methods=["GET", "POST"])
def pengaturan():
    """Tampilkan dan kelola halaman pengaturan waktu (Siswa, Guru/Staf, Keamanan)."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # Ambil data terbaru dari DB setiap kali route dipanggil
    setting_siswa = SettingWaktu.query.first()
    setting_guru_staf = SettingWaktuGuruStaf.query.first()

    shifts = ['shift1', 'shift2', 'shift3']
    settings_keamanan = {}
    for s in shifts:
        setting_keamanan = SettingWaktuKeamanan.query.filter_by(nama_shift=s).first()
        if not setting_keamanan:
            setting_keamanan = SettingWaktuKeamanan(nama_shift=s)
        settings_keamanan[s] = setting_keamanan

    # Handle POST (simpan siswa)
    if request.method == "POST":
        action = request.form.get("action")
        setting_type = request.form.get("setting_type")
        print("POST:", dict(request.form))

        if setting_type == "siswa" and action == "save_siswa":
            try:
                jam_masuk_mulai = request.form.get("jam_masuk_mulai")
                jam_masuk_selesai = request.form.get("jam_masuk_selesai")
                jam_pulang_mulai = request.form.get("jam_pulang_mulai")
                jam_pulang_selesai = request.form.get("jam_pulang_selesai")
                jam_terlambat_selesai = request.form.get("jam_terlambat_selesai")

                if not all([jam_masuk_mulai, jam_masuk_selesai, jam_pulang_mulai, jam_pulang_selesai]):
                    flash("Semua waktu wajib diisi (kecuali batas terlambat).", "danger")
                    return redirect(url_for("pengaturan"))

                # buat / update record
                if not setting_siswa:
                    setting_siswa = SettingWaktu()
                    db.session.add(setting_siswa)

                setting_siswa.jam_masuk_mulai = datetime.strptime(jam_masuk_mulai, "%H:%M").time()
                setting_siswa.jam_masuk_selesai = datetime.strptime(jam_masuk_selesai, "%H:%M").time()
                setting_siswa.jam_pulang_mulai = datetime.strptime(jam_pulang_mulai, "%H:%M").time()
                setting_siswa.jam_pulang_selesai = datetime.strptime(jam_pulang_selesai, "%H:%M").time()
                setting_siswa.jam_terlambat_selesai = (
                    datetime.strptime(jam_terlambat_selesai, "%H:%M").time()
                    if jam_terlambat_selesai else None
                )

                db.session.commit()
                flash("Pengaturan waktu siswa berhasil disimpan.", "success")

            except Exception as e:
                db.session.rollback()
                flash(f"Gagal menyimpan pengaturan siswa: {str(e)}", "danger")
                app.logger.exception("Error saving setting siswa")

        # setelah POST redirect kembali agar URL tetap bersih
        return redirect(url_for("pengaturan"))

    # Render page (tidak ada auto_open_modal di sini)
    return render_template(
        "pengaturan.html",
        setting_siswa_data=setting_siswa,
        setting_guru_staf=setting_guru_staf,
        settings_keamanan=settings_keamanan,
        shifts=shifts,
    )


# =======================================================================
#  API: Ambil data pengaturan siswa (dipanggil oleh JS ketika Reset diklik)
# =======================================================================
@app.route("/api/setting_siswa", methods=["GET"])
def api_get_setting_siswa():
    auth_check = check_admin_session()
    if auth_check:
        # Jika check_admin_session mengembalikan redirect/Response, kembalikan itu
        return auth_check

    setting = SettingWaktu.query.first()
    if not setting:
        data = {
            "jam_masuk_mulai": "",
            "jam_masuk_selesai": "",
            "jam_terlambat_selesai": "",
            "jam_pulang_mulai": "",
            "jam_pulang_selesai": ""
        }
    else:
        data = {
            "jam_masuk_mulai": setting.jam_masuk_mulai.strftime("%H:%M") if setting.jam_masuk_mulai else "",
            "jam_masuk_selesai": setting.jam_masuk_selesai.strftime("%H:%M") if setting.jam_masuk_selesai else "",
            "jam_terlambat_selesai": setting.jam_terlambat_selesai.strftime("%H:%M") if setting.jam_terlambat_selesai else "",
            "jam_pulang_mulai": setting.jam_pulang_mulai.strftime("%H:%M") if setting.jam_pulang_mulai else "",
            "jam_pulang_selesai": setting.jam_pulang_selesai.strftime("%H:%M") if setting.jam_pulang_selesai else ""
        }

    return jsonify(data)


@app.route("/pengaturan_pegawai", methods=["GET", "POST"])
def pengaturan_pegawai():
    """Menangani POST dari modal pengaturan waktu absensi pegawai (Guru/Staf/Keamanan)."""
    # Pastikan fungsi ini ditempatkan setelah definisi model dan db
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # UPDATE: Tambahkan 'shift4' ke daftar shift (jika diperlukan)
    shifts = ['shift1', 'shift2', 'shift3', 'shift4']
    settings_keamanan = {}
    setting_guru_staf = SettingWaktuGuruStaf.query.first()  # Diperlukan untuk logika save Guru/Staf
    for s in shifts:
        setting = SettingWaktuKeamanan.query.filter_by(nama_shift=s).first()
        if not setting:
            # Gunakan placeholder untuk GET (walaupun GET di-redirect ke /pengaturan)
            setting = type('SettingPlaceholder', (object,), {
                'id': None, 'jam_masuk_mulai': None, 'jam_masuk_selesai': None,
                'jam_pulang_mulai': None, 'jam_pulang_selesai': None,
                'jam_terlambat_selesai': None, 'nama_shift': s
            })()

        settings_keamanan[s] = setting

    if request.method == "POST":
        action = request.form.get("action")
        setting_type = request.form.get("setting_type")

        try:
            if action == "reset":
                if setting_type == "guru_staf" and setting_guru_staf and setting_guru_staf.id:
                    db.session.delete(setting_guru_staf)
                    flash("Pengaturan waktu Guru/Staf berhasil direset.", "success")
                elif setting_type == "keamanan_all":
                    # Reset semua shift keamanan (termasuk shift1, shift2, shift3, shift4)
                    SettingWaktuKeamanan.query.delete()
                    flash("Semua pengaturan shift Keamanan berhasil direset.", "success")
                elif setting_type in shifts:
                    # Reset shift spesifik
                    current_setting = SettingWaktuKeamanan.query.filter_by(nama_shift=setting_type).first()
                    if current_setting and current_setting.id:
                        db.session.delete(current_setting)
                        shift_display_name = setting_type.capitalize().replace('Shift', 'Shift ')
                        flash(f"Pengaturan waktu Keamanan {shift_display_name} berhasil direset.", "success")

                db.session.commit()

            elif action == "save":
                jam_masuk_mulai_str = request.form.get("jam_masuk_mulai")
                jam_masuk_selesai_str = request.form.get("jam_masuk_selesai")
                jam_pulang_mulai_str = request.form.get("jam_pulang_mulai")
                jam_pulang_selesai_str = request.form.get("jam_pulang_selesai")
                jam_terlambat_selesai_str = request.form.get("jam_terlambat_selesai")

                if not all([jam_masuk_mulai_str, jam_masuk_selesai_str, jam_pulang_mulai_str, jam_pulang_selesai_str]):
                    flash("Semua waktu wajib diisi (kecuali batas terlambat).", "danger")
                    return redirect(url_for("pengaturan"))

                # Konversi string waktu ke objek time
                jam_masuk_mulai = datetime.strptime(jam_masuk_mulai_str, "%H:%M").time()
                jam_masuk_selesai = datetime.strptime(jam_masuk_selesai_str, "%H:%M").time()
                jam_pulang_mulai = datetime.strptime(jam_pulang_mulai_str, "%H:%M").time()
                jam_pulang_selesai = datetime.strptime(jam_pulang_selesai_str, "%H:%M").time()
                jam_terlambat_selesai = datetime.strptime(jam_terlambat_selesai_str,
                                                          "%H:%M").time() if jam_terlambat_selesai_str else None

                if setting_type == "guru_staf":
                    # Simpan Guru/Staf
                    if not setting_guru_staf:
                        setting_guru_staf = SettingWaktuGuruStaf()
                        db.session.add(setting_guru_staf)

                    setting_guru_staf.jam_masuk_mulai = jam_masuk_mulai
                    setting_guru_staf.jam_masuk_selesai = jam_masuk_selesai
                    setting_guru_staf.jam_pulang_mulai = jam_pulang_mulai
                    setting_guru_staf.jam_pulang_selesai = jam_pulang_selesai
                    setting_guru_staf.jam_terlambat_selesai = jam_terlambat_selesai

                    flash("Pengaturan waktu Guru/Staf berhasil diperbarui.", "success")

                elif setting_type in shifts:
                    # Simpan Keamanan per shift
                    current_setting = SettingWaktuKeamanan.query.filter_by(nama_shift=setting_type).first()
                    if not current_setting:
                        current_setting = SettingWaktuKeamanan(nama_shift=setting_type)
                        db.session.add(current_setting)

                    current_setting.jam_masuk_mulai = jam_masuk_mulai
                    current_setting.jam_masuk_selesai = jam_masuk_selesai
                    current_setting.jam_pulang_mulai = jam_pulang_mulai
                    current_setting.jam_pulang_selesai = jam_pulang_selesai
                    current_setting.jam_terlambat_selesai = jam_terlambat_selesai

                    shift_display_name = setting_type.capitalize().replace('Shift', 'Shift ')
                    flash(
                        f"Pengaturan waktu Keamanan {shift_display_name} berhasil diperbarui.",
                        "success")

                db.session.commit()

            else:
                flash("Aksi tidak valid.", "danger")

        except ValueError:
            flash("Format waktu tidak valid, silakan coba lagi.", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Terjadi kesalahan saat menyimpan: {str(e)}", "danger")

        # Setelah POST, selalu redirect kembali ke halaman pengaturan utama
        return redirect(url_for("pengaturan"))

    # Jika GET request, redirect ke halaman pengaturan utama
    return redirect(url_for("pengaturan"))

# =======================================================================
#  MAIN EXECUTION
# =======================================================================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")