from datetime import datetime
from flask import render_template, jsonify, Blueprint, request
from models import (
    Siswa, SettingWaktu, Absensi, Pegawai,
    AbsensiPegawai, SettingWaktuGuruStaf,
    SettingWaktuKeamanan, db
)
from utils import format_nomor_hp
import requests

scan_bp = Blueprint("scan_bp", __name__, url_prefix="/scan")

# =======================================================================
#  ROUTE: HALAMAN SCAN QR
# =======================================================================
@scan_bp.route("/")
def scan():
    """Tampilkan halaman scanner QR."""
    return render_template("scan.html")


# =======================================================================
#  ROUTE: PROSES SUBMIT QR
# =======================================================================
@scan_bp.route("/submit_scan", methods=["POST"])
def submit_scan():
    """Proses hasil scan QR untuk mencatat absensi."""
    qr_data = request.form.get("qr_data") or request.form.get("identifier")

    if not qr_data:
        return jsonify({'status': 'danger', 'message': 'Data QR tidak ditemukan.'})

    qr_data = qr_data.strip().lower()
    if len(qr_data) < 2:
        return jsonify({'status': 'danger', 'message': 'Format QR tidak valid. Data terlalu pendek.'})

    prefix = qr_data[0]
    identifier = qr_data[1:]

    now = datetime.now()
    hari_ini = now.date()
    waktu_skrg = now.time()

    entity = None
    model = None
    setting = None
    field = None
    send_wa = False
    role = None
    shift = None

    # ====================== SISWA ======================
    if prefix == 's':
        entity = Siswa.query.filter_by(nis=identifier).first()
        if not entity:
            return jsonify({'status': 'danger', 'message': f'Siswa dengan NIS {identifier} tidak ditemukan.'})

        model = Absensi
        field = "nis"
        setting = SettingWaktu.query.first()
        send_wa = True

    # ====================== PEGAWAI ======================
    elif prefix == 'p':
        entity = Pegawai.query.filter_by(no_id=identifier).first()
        if not entity:
            return jsonify({'status': 'danger', 'message': f'Pegawai dengan ID {identifier} tidak ditemukan.'})

        model = AbsensiPegawai
        field = "no_id"
        role = entity.role

        if role in ('guru', 'staf'):
            setting = SettingWaktuGuruStaf.query.first()
        elif role == 'keamanan':
            shift = entity.shift
            if shift:
                setting = SettingWaktuKeamanan.query.filter_by(nama_shift=shift).first()
            else:
                return jsonify({'status': 'danger', 'message': 'Pegawai keamanan belum memiliki shift.'})
        else:
            return jsonify({'status': 'danger', 'message': f'Role {role} tidak dikenali.'})

    else:
        return jsonify({'status': 'danger', 'message': 'Format QR tidak valid. Gunakan format S<ID> atau P<ID>.'})

    if not setting:
        return jsonify({'status': 'danger', 'message': 'Pengaturan waktu absensi belum diatur oleh admin.'})

    # ====================== CEK WAKTU ABSEN ======================
    if setting.jam_masuk_mulai <= waktu_skrg <= setting.jam_masuk_selesai:
        jenis_absen = "masuk"
        status_absen_db = "Hadir"
    elif setting.jam_terlambat_selesai and setting.jam_masuk_selesai < waktu_skrg <= setting.jam_terlambat_selesai:
        jenis_absen = "masuk"
        status_absen_db = "Terlambat"
    elif setting.jam_pulang_mulai <= waktu_skrg <= setting.jam_pulang_selesai:
        jenis_absen = "pulang"
        status_absen_db = "Hadir"
    else:
        return jsonify({'status': 'danger', 'message': 'Bukan waktu absensi yang valid.'})

    # ====================== CEK SUDAH ABSEN BELUM ======================
    filter_conditions = {field: identifier, "tanggal": hari_ini, "jenis_absen": jenis_absen}
    sudah_absen = model.query.filter_by(**filter_conditions).first()
    if sudah_absen:
        return jsonify({'status': 'warning', 'message': f"{entity.nama} sudah absen {jenis_absen} hari ini."})

    # ====================== SIMPAN ABSENSI ======================
    absensi_data = {
        field: identifier,
        "status": status_absen_db,
        "jenis_absen": jenis_absen,
        "tanggal": hari_ini,
        "waktu": now.time()
    }

    try:
        db.session.add(model(**absensi_data))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Database Error:", e)
        return jsonify({'status': 'danger', 'message': 'Gagal menyimpan data absensi.'})

    # ====================== KIRIM WHATSAPP (HANYA SISWA) ======================
    if send_wa and entity.no_hp_ortu:
        nomor = format_nomor_hp(entity.no_hp_ortu)
        pesan = (
            f"📚 *Notifikasi Absensi Sekolah*\n\n"
            f"Anak Anda, {entity.nama}, telah melakukan absen *{jenis_absen}* "
            f"dengan status *{status_absen_db}* pada pukul {now.strftime('%H:%M:%S')}."
        )

        try:
            token = "m7sWNBLHrGi2AHZNj2x3"  # Ganti dengan token kamu sendiri
            response = requests.post(
                "https://api.fonnte.com/send",
                headers={"Authorization": token},
                data={"target": nomor, "message": pesan}
            )

            if response.status_code == 200:
                return jsonify({'status': 'success', 'message': f"Absen {jenis_absen} berhasil & WA terkirim."})
            else:
                return jsonify({'status': 'warning', 'message': f"Absen berhasil tapi WA gagal. ({response.status_code})"})

        except Exception as e:
            print("WA Error:", e)
            return jsonify({'status': 'warning', 'message': f"Absen berhasil tapi WA gagal: {str(e)}"})

    return jsonify({'status': 'success', 'message': f"Absen {jenis_absen} berhasil ({status_absen_db})."})