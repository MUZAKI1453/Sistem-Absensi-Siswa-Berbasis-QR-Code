import calendar as cal
from datetime import datetime, date
import io
import csv

from flask import (
    Blueprint, Response, render_template, flash, redirect,
    url_for, request, current_app
)
from sqlalchemy import select, delete

from models import JadwalKeamanan, Pegawai, db
from utils import check_admin_session

# Inisialisasi Blueprint
jadwal_keamanan_bp = Blueprint("jadwal_keamanan_bp", __name__, url_prefix="/jadwal_keamanan")


# ==============================================================================
# HALAMAN UTAMA JADWAL KEAMANAN
# (Tidak ada perubahan)
# ==============================================================================
@jadwal_keamanan_bp.route("/", methods=["GET"])
def jadwal_keamanan():
    """Tampilkan halaman pengaturan jadwal keamanan bulanan."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    try:
        current_month = int(request.args.get("month", datetime.now().month))
        current_year = int(request.args.get("year", datetime.now().year))
    except (ValueError, TypeError):
        current_month = datetime.now().month
        current_year = datetime.now().year

    if not (1 <= current_month <= 12 and current_year >= 2023):
        current_month = datetime.now().month
        current_year = datetime.now().year

    current_date = datetime(current_year, current_month, 1)
    days_in_month = cal.monthrange(current_year, current_month)[1]

    security_staff = get_security_staff()
    if isinstance(security_staff, Response):
        return security_staff

    staff_schedules = get_monthly_schedule(current_month, current_year)
    if isinstance(staff_schedules, Response):
        return staff_schedules

    return render_template(
        "jadwal_keamanan.html",
        security_staff=security_staff,
        staff_schedules=staff_schedules,
        current_date=current_date,
        current_month=current_month,
        current_year=current_year,
        days_in_month=days_in_month,
        datetime=datetime,
        date=date
    )


# ==============================================================================
# SIMPAN JADWAL KEAMANAN
# (Tidak ada perubahan)
# ==============================================================================
@jadwal_keamanan_bp.route("/simpan", methods=["POST"])
def simpan_jadwal_keamanan():
    """Simpan data jadwal shift keamanan dari form."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    form_data = request.form
    try:
        current_month = int(form_data.get("month"))
        current_year = int(form_data.get("year"))
    except (ValueError, TypeError):
        flash("Format bulan atau tahun tidak valid.", "danger")
        return redirect(url_for("jadwal_keamanan_bp.jadwal_keamanan"))

    success = save_monthly_schedule(current_month, current_year, form_data)

    if isinstance(success, Response):
        return success

    if success:
        flash(f"Jadwal keamanan bulan {current_month}/{current_year} berhasil disimpan.", "success")
    else:
        flash("Gagal menyimpan jadwal ke database.", "danger")

    return redirect(url_for("jadwal_keamanan_bp.jadwal_keamanan", month=current_month, year=current_year))


# ==============================================================================
# COPY JADWAL BULAN SEBELUMNYA
# (Tidak ada perubahan)
# ==============================================================================
@jadwal_keamanan_bp.route("/copy-previous", methods=["POST"])
def copy_previous_schedule():
    """Menyalin jadwal bulan sebelumnya ke bulan ini (hanya slot kosong)."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    try:
        current_month = int(request.form.get("current_month"))
        current_year = int(request.form.get("current_year"))
    except (ValueError, TypeError):
        flash("Format bulan/tahun tidak valid.", "danger")
        return redirect(url_for("jadwal_keamanan_bp.jadwal_keamanan"))

    prev_month = current_month - 1 if current_month > 1 else 12
    prev_year = current_year if current_month > 1 else current_year - 1
    days_in_month = cal.monthrange(current_year, current_month)[1]

    security_staff = get_security_staff()
    if isinstance(security_staff, Response):
        return security_staff
    security_staff_ids = [s["id"] for s in security_staff]

    try:
        prev_schedules = get_monthly_schedule(prev_month, prev_year)
        if isinstance(prev_schedules, Response):
            return prev_schedules

        prev_map = {
            sid: {datetime.strptime(d, "%Y-%m-%d").day: s for d, s in shifts.items()}
            for sid, shifts in prev_schedules.items()
        }

        curr_schedules = get_monthly_schedule(current_month, current_year)
        if isinstance(curr_schedules, Response):
            return curr_schedules

        curr_set = set()
        for sid, dates in curr_schedules.items():
            for d in dates.keys():
                curr_set.add((sid, datetime.strptime(d, "%Y-%m-%d").date()))

        copied_count = 0
        for sid in security_staff_ids:
            if sid not in prev_map:
                continue
            for day in range(1, days_in_month + 1):
                tgl = date(current_year, current_month, day)
                if (sid, tgl) in curr_set:
                    continue
                shift = prev_map[sid].get(day)
                if shift and shift.strip() != "":
                    db.session.add(JadwalKeamanan(pegawai_id=sid, tanggal=tgl, shift=shift))
                    copied_count += 1

        db.session.commit()
        flash(f"Berhasil menyalin {copied_count} jadwal dari bulan sebelumnya.", "success")

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error copying schedules: {e}")
        flash("Gagal menyalin jadwal dari bulan sebelumnya.", "danger")

    return redirect(url_for("jadwal_keamanan_bp.jadwal_keamanan", month=current_month, year=current_year))


# ==============================================================================
# UTILITAS INTERNAL
# (Tidak ada perubahan)
# ==============================================================================

def get_security_staff():
    """Mengambil daftar pegawai dengan Role 'keamanan'."""
    try:
        staff_objects = db.session.execute(
            select(Pegawai).filter_by(role="keamanan").order_by(Pegawai.nama.asc())
        ).scalars().all()

        return [{"id": s.id, "nama": s.nama} for s in staff_objects]
    except Exception as e:
        current_app.logger.error(f"Error fetching security staff: {e}")
        return []


def get_monthly_schedule(month, year):
    """Ambil jadwal keamanan untuk bulan dan tahun tertentu."""
    try:
        days_in_month = cal.monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)

        records = db.session.execute(
            select(JadwalKeamanan).filter(
                JadwalKeamanan.tanggal.between(start_date, end_date)
            )
        ).scalars().all()

        schedule = {}
        for r in records:
            staff_id = r.pegawai_id
            date_str = r.tanggal.strftime("%Y-%m-%d")
            if staff_id not in schedule:
                schedule[staff_id] = {}
            schedule[staff_id][date_str] = r.shift

        return schedule
    except Exception as e:
        current_app.logger.error(f"Error fetching monthly schedule: {e}")
        return {}


def save_monthly_schedule(month, year, form_data):
    """Simpan atau perbarui jadwal keamanan bulanan ke database."""
    try:
        days_in_month = cal.monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)

        security_staff = get_security_staff()
        staff_ids = [s["id"] for s in security_staff]
        updates = []

        for key, val in form_data.items():
            if not key.startswith("schedule_"):
                continue

            parts = key.split("_")
            if len(parts) != 3:
                continue

            pegawai_id = int(parts[1])
            tanggal_str = parts[2]

            try:
                tanggal_obj = datetime.strptime(tanggal_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            if start_date <= tanggal_obj <= end_date:
                updates.append(
                    {"pegawai_id": pegawai_id, "tanggal": tanggal_obj, "shift": val}
                )

        # Hapus jadwal lama untuk bulan ini
        db.session.execute(
            delete(JadwalKeamanan).filter(
                JadwalKeamanan.tanggal.between(start_date, end_date),
                JadwalKeamanan.pegawai_id.in_(staff_ids),
            )
        )

        # Tambahkan data baru
        for item in updates:
            if item["shift"] and item["shift"].strip() != "":
                db.session.add(
                    JadwalKeamanan(
                        pegawai_id=item["pegawai_id"],
                        tanggal=item["tanggal"],
                        shift=item["shift"],
                    )
                )

        db.session.commit()
        return True

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving schedule: {e}")
        return False


# ==============================================================================
# ROUTE BARU (DIPERBARUI): IMPOR JADWAL KEAMANAN DARI CSV
# ==============================================================================
@jadwal_keamanan_bp.route("/impor", methods=["POST"])
def impor_jadwal_keamanan():
    """Impor jadwal keamanan dari file CSV."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # 1. Validasi Input Form
    if "csv_file" not in request.files:
        flash("File CSV tidak ditemukan.", "danger")
        return redirect(url_for("jadwal_keamanan_bp.jadwal_keamanan"))

    file = request.files["csv_file"]
    if file.filename == "" or not file.filename.endswith(".csv"):
        flash("Nama file tidak valid atau bukan format .csv", "danger")
        return redirect(url_for("jadwal_keamanan_bp.jadwal_keamanan"))

    try:
        # Ambil bulan dan tahun dari form modal
        bulan_impor = int(request.form.get("import_bulan"))
        tahun_impor = int(request.form.get("import_tahun"))
        if not (1 <= bulan_impor <= 12):
            raise ValueError("Bulan tidak valid")
    except (ValueError, TypeError):
        flash("Bulan atau Tahun impor tidak valid.", "danger")
        return redirect(url_for("jadwal_keamanan_bp.jadwal_keamanan"))

    # 2. Proses File CSV
    try:
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        csv_input = csv.DictReader(stream)

        count_jadwal_baru = 0
        pegawai_diproses = set()

        # Tentukan tanggal awal dan akhir untuk menghapus data lama
        start_date = date(tahun_impor, bulan_impor, 1)
        days_in_month = cal.monthrange(tahun_impor, bulan_impor)[1]
        end_date = date(tahun_impor, bulan_impor, days_in_month)

        for row in csv_input:
            no_id = row.get("No_id") or row.get("no_id")

            if not no_id:
                flash(f"Baris data tidak valid (No_id kosong), dilewati.", "warning")
                continue

            # 3. Validasi Data per Baris
            pegawai = Pegawai.query.filter_by(no_id=no_id).first()
            if not pegawai:
                flash(f"Pegawai dengan No ID '{no_id}' (dari file CSV) tidak ditemukan, dilewati.", "warning")
                continue

            # 4. Hapus Jadwal Lama (PENTING!)
            if pegawai.id not in pegawai_diproses:
                try:
                    # Hapus semua jadwal di bulan & tahun itu untuk pegawai ini
                    db.session.execute(
                        delete(JadwalKeamanan).filter(
                            JadwalKeamanan.pegawai_id == pegawai.id,
                            JadwalKeamanan.tanggal.between(start_date, end_date)
                        )
                    )
                    pegawai_diproses.add(pegawai.id)
                except Exception as e:
                    db.session.rollback()
                    flash(f"Gagal menghapus jadwal lama untuk {no_id}: {e}", "danger")
                    continue

            # 5. Loop dan Tambah Jadwal Baru
            for i in range(1, days_in_month + 1): # Hanya loop sampai hari terakhir di bulan
                col_name = f"shift_tgl{i}"
                shift_value = row.get(col_name)

                # Jika kolom shift ada isinya (tidak kosong)
                if shift_value and shift_value.strip() != "":
                    try:
                        tgl_obj = date(tahun_impor, bulan_impor, i)
                        
                        jadwal_baru = JadwalKeamanan(
                            pegawai_id=pegawai.id,
                            tanggal=tgl_obj,
                            shift=shift_value.strip()
                        )
                        db.session.add(jadwal_baru)
                        count_jadwal_baru += 1

                    except ValueError:
                        # Seharusnya tidak terjadi karena sudah dibatasi days_in_month
                        continue 

        # 6. Commit ke Database
        db.session.commit()
        flash(f"Impor jadwal berhasil. {count_jadwal_baru} entri jadwal baru ditambahkan/diperbarui.", "success")

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat impor CSV jadwal: {e}")
        flash(f"Terjadi kesalahan besar saat memproses file: {e}", "danger")

    # Redirect kembali ke halaman yang menampilkan bulan dan tahun yang baru diimpor
    return redirect(url_for("jadwal_keamanan_bp.jadwal_keamanan", month=bulan_impor, year=tahun_impor))