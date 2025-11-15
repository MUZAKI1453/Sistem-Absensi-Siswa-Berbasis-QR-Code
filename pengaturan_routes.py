# File: pengaturan_routes.py
# (Ini adalah versi yang sudah disesuaikan dengan tata letak modal yang Anda minta)

import os
from datetime import datetime
from sqlalchemy import exc
from flask import (
    Blueprint, render_template, request, redirect, url_for, session,
    jsonify, flash
)
from models import (
    db, SettingWaktu, SettingWaktuGuruStaf,
    SettingWaktuKeamanan, HariLibur
)
from utils import check_admin_session

# Buat Blueprint
pengaturan_bp = Blueprint("pengaturan_bp", __name__)


# =======================================================================
#  ROUTE: PENGATURAN UMUM (GET / POST)
# =======================================================================
@pengaturan_bp.route("/pengaturan", methods=["GET", "POST"])
def pengaturan():
    """Tampilkan dan kelola halaman pengaturan."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # --- LOGIKA POST (HANYA UNTUK SIMPAN WAKTU SISWA) ---
    if request.method == "POST":
        action = request.form.get("action")
        setting_type = request.form.get("setting_type")

        if setting_type == "siswa" and action == "save_siswa":
            try:
                setting_siswa = SettingWaktu.query.first()
                if not setting_siswa:
                    setting_siswa = SettingWaktu()
                    db.session.add(setting_siswa)

                jam_masuk_mulai = request.form.get("jam_masuk_mulai")
                jam_masuk_selesai = request.form.get("jam_masuk_selesai")
                jam_pulang_mulai = request.form.get("jam_pulang_mulai")
                jam_pulang_selesai = request.form.get("jam_pulang_selesai")
                jam_terlambat_selesai = request.form.get("jam_terlambat_selesai")

                if not all([jam_masuk_mulai, jam_masuk_selesai, jam_pulang_mulai, jam_pulang_selesai]):
                    flash("Semua waktu wajib diisi (kecuali batas terlambat).", "danger")
                else:
                    setting_siswa.jam_masuk_mulai = datetime.strptime(jam_masuk_mulai, "%H:%M").time()
                    setting_siswa.jam_masuk_selesai = datetime.strptime(jam_masuk_selesai, "%H:%M").time()
                    setting_siswa.jam_pulang_mulai = datetime.strptime(jam_pulang_mulai, "%H:%M").time()
                    setting_siswa.jam_pulang_selesai = datetime.strptime(jam_pulang_selesai, "%H:%M").time()
                    setting_siswa.jam_terlambat_selesai = (
                        datetime.strptime(jam_terlambat_selesai, "%H:%M").time() if jam_terlambat_selesai else None)
                    db.session.commit()
                    flash("Pengaturan waktu siswa berhasil disimpan.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Gagal menyimpan pengaturan siswa: {str(e)}", "danger")

        return redirect(url_for("pengaturan_bp.pengaturan"))

    # --- LOGIKA GET (MENAMPILKAN SEMUA DATA PENGATURAN) ---
    setting_siswa = SettingWaktu.query.first()
    setting_guru_staf = SettingWaktuGuruStaf.query.first()
    shifts = ['shift1', 'shift2', 'shift3', 'shift4']
    settings_keamanan = {
        s: SettingWaktuKeamanan.query.filter_by(nama_shift=s).first() or SettingWaktuKeamanan(nama_shift=s) for s in
        shifts}

    # Ambil data hari libur spesial
    daftar_hari_libur = HariLibur.query.order_by(HariLibur.tanggal.asc()).all()

    # Ambil data hari libur rutin (Siswa)
    hari_libur_rutin_tersimpan = []
    if setting_siswa and setting_siswa.hari_libur_rutin:
        hari_libur_rutin_tersimpan = setting_siswa.hari_libur_rutin.split(',')

    # Ambil data libur rutin Guru/Staf
    hari_libur_rutin_pegawai_tersimpan = []
    if setting_guru_staf and setting_guru_staf.hari_libur_rutin:
        hari_libur_rutin_pegawai_tersimpan = setting_guru_staf.hari_libur_rutin.split(',')

    semua_hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

    return render_template(
        "pengaturan.html",
        setting_siswa_data=setting_siswa,
        setting_guru_staf=setting_guru_staf,
        settings_keamanan=settings_keamanan,
        shifts=shifts,
        daftar_hari_libur=daftar_hari_libur,
        hari_libur_rutin_tersimpan=hari_libur_rutin_tersimpan,
        hari_libur_rutin_pegawai_tersimpan=hari_libur_rutin_pegawai_tersimpan,
        semua_hari=semua_hari
    )


# =======================================================================
#  ROUTE: KELOLA HARI LIBUR (TELAH DIPERBARUI)
# =======================================================================
@pengaturan_bp.route("/hari_libur", methods=["POST"])
def kelola_hari_libur():
    auth_check = check_admin_session()
    if auth_check: return auth_check

    action = request.form.get("action")

    # --- Aksi Menyimpan Hari Libur Rutin (Siswa) ---
    if action == "simpan_rutin_siswa":
        setting_waktu = SettingWaktu.query.first()
        if not setting_waktu:
            flash("Harap simpan 'Pengaturan Waktu Siswa' setidaknya sekali sebelum mengatur hari libur rutin.", "warning")
            return redirect(url_for("pengaturan_bp.pengaturan"))

        libur_rutin_terpilih = request.form.getlist('hari_rutin_siswa')
        setting_waktu.hari_libur_rutin = ",".join(libur_rutin_terpilih)
        db.session.commit()
        flash("Pengaturan hari libur rutin (Siswa) berhasil disimpan.", "success")

    # ==============================================================================
    #  PERUBAHAN: Menambahkan logika 'simpan_rutin_pegawai'
    # ==============================================================================
    elif action == "simpan_rutin_pegawai":
        setting_pegawai = SettingWaktuGuruStaf.query.first()
        if not setting_pegawai:
            flash("Harap simpan 'Pengaturan Waktu Pegawai' setidaknya sekali sebelum mengatur hari libur rutin.", "warning")
            return redirect(url_for("pengaturan_bp.pengaturan"))

        libur_rutin_terpilih = request.form.getlist('hari_rutin_pegawai')
        setting_pegawai.hari_libur_rutin = ",".join(libur_rutin_terpilih)
        db.session.commit()
        flash("Pengaturan hari libur rutin (Guru & Staf) berhasil disimpan.", "success")
    # ==============================================================================

    # --- Aksi Menambah Hari Libur Spesial ---
    elif action == "tambah_spesial":
        tanggal_str = request.form.get("tanggal")
        keterangan = request.form.get("keterangan")
        if not tanggal_str or not keterangan:
            flash("Tanggal dan Keterangan wajib diisi.", "danger")
            return redirect(url_for("pengaturan_bp.pengaturan"))
        try:
            tanggal_obj = datetime.strptime(tanggal_str, "%Y-%m-%d").date()
            libur_baru = HariLibur(tanggal=tanggal_obj, keterangan=keterangan)
            db.session.add(libur_baru)
            db.session.commit()
            flash(f"Hari libur spesial pada {tanggal_str} berhasil ditambahkan.", "success")
        except exc.IntegrityError:
            db.session.rollback()
            flash(f"Tanggal {tanggal_str} sudah terdaftar sebagai hari libur.", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Terjadi kesalahan: {str(e)}", "danger")

    # --- Aksi Menghapus Hari Libur Spesial ---
    elif action == "hapus_spesial":
        libur_id = request.form.get("id")
        libur_to_delete = HariLibur.query.get(libur_id)
        if libur_to_delete:
            db.session.delete(libur_to_delete)
            db.session.commit()
            flash("Hari libur spesial berhasil dihapus.", "success")
        else:
            flash("Hari libur tidak ditemukan.", "danger")

    return redirect(url_for("pengaturan_bp.pengaturan"))


# =======================================================================
#  ROUTE: API SETTING SISWA (Tidak Berubah)
# =======================================================================
@pengaturan_bp.route("/api/setting_siswa", methods=["GET"])
def api_get_setting_siswa():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    setting = SettingWaktu.query.first()
    data = {
        "jam_masuk_mulai": setting.jam_masuk_mulai.strftime("%H:%M") if setting and setting.jam_masuk_mulai else "",
        "jam_masuk_selesai": setting.jam_masuk_selesai.strftime(
            "%H:%M") if setting and setting.jam_masuk_selesai else "",
        "jam_terlambat_selesai": setting.jam_terlambat_selesai.strftime(
            "%H:%M") if setting and setting.jam_terlambat_selesai else "",
        "jam_pulang_mulai": setting.jam_pulang_mulai.strftime("%H:%M") if setting and setting.jam_pulang_mulai else "",
        "jam_pulang_selesai": setting.jam_pulang_selesai.strftime(
            "%H:%M") if setting and setting.jam_pulang_selesai else ""
    }
    return jsonify(data)


# =======================================================================
#  ROUTE: PENGATURAN PEGAWAI (TELAH DIPERBARUI)
# =======================================================================
@pengaturan_bp.route("/pengaturan_pegawai", methods=["GET", "POST"])
def pengaturan_pegawai():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    shifts = ['shift1', 'shift2', 'shift3', 'shift4']
    setting_guru_staf = SettingWaktuGuruStaf.query.first()

    if request.method == "POST":
        action = request.form.get("action")
        setting_type = request.form.get("setting_type")

        try:
            if action == "reset":
                if setting_type == "guru_staf" and setting_guru_staf and setting_guru_staf.id:
                    db.session.delete(setting_guru_staf)
                    flash("Pengaturan waktu Guru/Staf berhasil direset.", "success")
                elif setting_type == "keamanan_all":
                    SettingWaktuKeamanan.query.delete()
                    flash("Semua pengaturan shift Keamanan berhasil direset.", "success")
                elif setting_type in shifts:
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
                else:
                    jam_masuk_mulai = datetime.strptime(jam_masuk_mulai_str, "%H:%M").time()
                    jam_masuk_selesai = datetime.strptime(jam_masuk_selesai_str, "%H:%M").time()
                    jam_pulang_mulai = datetime.strptime(jam_pulang_mulai_str, "%H:%M").time()
                    jam_pulang_selesai = datetime.strptime(jam_pulang_selesai_str, "%H:%M").time()
                    jam_terlambat_selesai = datetime.strptime(jam_terlambat_selesai_str,
                                                              "%H:%M").time() if jam_terlambat_selesai_str else None

                    if setting_type == "guru_staf":
                        if not setting_guru_staf:
                            setting_guru_staf = SettingWaktuGuruStaf()
                            db.session.add(setting_guru_staf)
                        setting_guru_staf.jam_masuk_mulai = jam_masuk_mulai
                        setting_guru_staf.jam_masuk_selesai = jam_masuk_selesai
                        setting_guru_staf.jam_pulang_mulai = jam_pulang_mulai
                        setting_guru_staf.jam_pulang_selesai = jam_pulang_selesai
                        setting_guru_staf.jam_terlambat_selesai = jam_terlambat_selesai
                        
                        # ==============================================================================
                        #  PERUBAHAN: Menghapus logika penyimpanan libur dari sini
                        # ==============================================================================
                        # libur_rutin_pegawai_terpilih = request.form.getlist('hari_rutin_pegawai')
                        # setting_guru_staf.hari_libur_rutin = ",".join(libur_rutin_pegawai_terpilih)
                        flash("Pengaturan waktu Guru/Staf berhasil diperbarui.", "success")
                        # ==============================================================================

                    elif setting_type in shifts:
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
                        flash(f"Pengaturan waktu Keamanan {shift_display_name} berhasil diperbarui.", "success")

                    db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Terjadi kesalahan saat menyimpan: {str(e)}", "danger")

    return redirect(url_for("pengaturan_bp.pengaturan"))