from datetime import datetime
from urllib import request
import requests
from flask import render_template, jsonify, Blueprint
from models import Siswa, SettingWaktu, Absensi, Pegawai, AbsensiPegawai, SettingWaktuGuruStaf, SettingWaktuKeamanan, db
from utils import format_nomor_hp

scan_bp = Blueprint("scan_bp", __name__, url_prefix="/scan")

# =======================================================================
#  ROUTE: PROSES ABSENSI & SCANNER
# =======================================================================
@scan_bp.route("/scan")
def scan():
    """Tampilkan halaman scanner QR."""
    return render_template("scan.html")


@scan_bp.route("/submit_scan", methods=["POST"])
def submit_scan():
    """Proses hasil scan QR untuk mencatat absensi menggunakan prefiks S dan P."""
    qr_data = request.form.get("qr_data") or request.form.get("identifier")

    if not qr_data:
        return jsonify({'status': 'danger', 'message': 'Data QR tidak ditemukan'})

    # Normalisasi data QR (membersihkan spasi dan mengubah ke huruf kecil)
    qr_data_normalized = qr_data.strip().lower()

    if len(qr_data_normalized) < 2:
        return jsonify({'status': 'danger', 'message': 'Format QR tidak valid. Data terlalu pendek.'})

    prefix = qr_data_normalized[0]  # Karakter pertama adalah prefiks
    identifier = qr_data_normalized[1:]  # Sisanya adalah ID

    now = datetime.now()
    hari_ini = now.date()
    waktu_skrg = now.time()

    entitas_type = None
    entity = None
    setting = None
    model = None
    field = None
    send_wa = False
    role = None
    shift = None

    # ================= PARSING DATA QR (MENGGUNAKAN PREFIKS S/P) =================

    # --- SISWA (Format: S<NIS>) ---
    if prefix == 's':
        entitas_type = "siswa"
        entity = Siswa.query.filter_by(nis=identifier).first()
        setting = SettingWaktu.query.first()  # Pengaturan Siswa Global
        model = Absensi
        field = "nis"
        send_wa = True

    # --- PEGAWAI (Format: P<No ID>) ---
    elif prefix == 'p':
        entitas_type = "pegawai"
        entity = Pegawai.query.filter_by(no_id=identifier).first()

        # Menggunakan model AbsensiPegawai (PERBAIKAN)
        model = AbsensiPegawai
        field = "no_id"
        send_wa = False

        if entity:
            role = entity.role

            # --- LOGIKA PENENTUAN SETTING WAKTU PEGAWAI ---
            if role == 'guru' or role == 'staf':
                # Guru dan Staf menggunakan SettingWaktuGuruStaf (PERBAIKAN)
                setting = SettingWaktuGuruStaf.query.first()

            elif role == 'keamanan':
                shift = entity.shift
                if shift:
                    # Keamanan menggunakan SettingWaktuKeamanan berdasarkan shift (PERBAIKAN)
                    setting = SettingWaktuKeamanan.query.filter_by(nama_shift=shift).first()
                else:
                    return jsonify({'status': 'danger',
                                    'message': f'Pegawai Keamanan harus memiliki data shift yang terisi. Hubungi Admin.'})

        else:
            return jsonify({'status': 'danger', 'message': f'Pegawai dengan ID {identifier} tidak ditemukan.'})

    else:
        # Jika format tidak dimulai dengan 's' atau 'p'
        return jsonify({'status': 'danger', 'message': 'Format QR tidak valid. Gunakan format S<ID> atau P<ID>.'})

    # ================= CEK VALIDASI & PROSES ABSENSI =================

    if not entity:
        return jsonify(
            {'status': 'danger', 'message': f'{entitas_type.capitalize()} dengan ID {identifier} tidak ditemukan.'})

    if not setting:
        return jsonify({'status': 'danger',
                        'message': f'Pengaturan waktu absensi untuk {role if entitas_type == "pegawai" else "Umum"} belum dibuat oleh admin'})

    # ================= CEK WAKTU ABSENSI =================
    jenis_absen = None
    status_absen_db = None
    pesan_status_wa = None

    if setting.jam_masuk_mulai <= waktu_skrg <= setting.jam_masuk_selesai:
        jenis_absen = "masuk"
        status_absen_db = "Hadir"
        pesan_status_wa = "Hadir"
    elif setting.jam_terlambat_selesai and setting.jam_masuk_selesai < waktu_skrg <= setting.jam_terlambat_selesai:
        jenis_absen = "masuk"
        status_absen_db = "Terlambat"
        pesan_status_wa = "Terlambat"
    elif setting.jam_pulang_mulai <= waktu_skrg <= setting.jam_pulang_selesai:
        jenis_absen = "pulang"
        status_absen_db = "Hadir"
        pesan_status_wa = "Hadir"
    else:
        return jsonify({'status': 'danger', 'message': 'Bukan waktu absensi yang valid saat ini.'})

    # ================= CEK SUDAH ABSEN BELUM =================
    filter_conditions = {
        field: identifier,
        "tanggal": hari_ini,
        "jenis_absen": jenis_absen
    }
    sudah_absen = model.query.filter_by(**filter_conditions).first()
    if sudah_absen:
        return jsonify({'status': 'warning', 'message': f"{entity.nama} sudah absen {jenis_absen} hari ini."})

    # ================= SIMPAN ABSENSI =================
    absensi_data = {
        field: identifier,
        "status": status_absen_db,
        "jenis_absen": jenis_absen,
        "tanggal": hari_ini,
        "waktu": now.time()
    }

    absensi = model(**absensi_data)

    try:
        db.session.add(absensi)
        # Commit database setelah proses WA berhasil (dipindahkan ke bawah, atau commit di sini jika tidak ada WA)
    except Exception as e:
        db.session.rollback()
        print(f"DATABASE ERROR: Gagal menyimpan absensi: {e}")
        return jsonify({'status': 'danger', 'message': 'Gagal menyimpan data absensi ke database.'})

    # ================= NOTIFIKASI WHATSAPP (hanya siswa) =================
    if send_wa and entitas_type == "siswa" and entity.no_hp_ortu:
        nomor = format_nomor_hp(entity.no_hp_ortu)
        pesan = f"Anak Anda, {entity.nama} ({entity.id}), telah absen {jenis_absen} dengan status {status_absen_db} pada {now.strftime('%H:%M')}."

        try:
            # Menggunakan MockRequests
            FONNTE_TOKEN = "m7sWNBLHrGi2AHZNj2x3"
            url = "https://api.fonnte.com/send"
            headers = {"Authorization": FONNTE_TOKEN}
            data = {"target": nomor, "message": pesan}
            response = requests.post(url, headers=headers, data=data)

            db.session.commit()  # Commit database setelah proses WA berhasil

            if response.status_code == 200:
                return jsonify({'status': 'success',
                                'message': f"Absen {jenis_absen} berhasil ({status_absen_db}) & WA terkirim."})

            return jsonify({'status': 'warning',
                            'message': f"Absen {jenis_absen} berhasil ({status_absen_db}), tapi WA gagal. Kode: {response.status_code}"})

        except Exception as e:
            # db.session.rollback() # Jika menggunakan SQLAlchemy
            db.session.commit()  # Commit jika absensi sudah sukses dicatat
            return jsonify({'status': 'warning',
                            'message': f"Absen {jenis_absen} berhasil ({status_absen_db}), tapi WA gagal: {str(e)}"})

    else:
        db.session.commit()  # Commit database jika tidak ada WA yang dikirim
        return jsonify({'status': 'success', 'message': f"Absen {jenis_absen} berhasil ({status_absen_db})."})