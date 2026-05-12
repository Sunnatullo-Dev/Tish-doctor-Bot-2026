"""JSON persistence for clinics, appointments, admins, and diagnosis tickets."""

import copy as copy_module
import sys

from clinic_bot import shared as s


def load_data():
    with s.data_lock:
        if not s.os.path.exists(s.DATA_FILE):
            s.logger.info("No data file found ? using defaults")
            s.data_loaded_successfully = True
            return
        try:
            with open(s.DATA_FILE, "r", encoding="utf-8") as f:
                data = s.json.load(f)

            loaded_clinics = data.get("clinics")
            if isinstance(loaded_clinics, list):
                s.clinics[:] = loaded_clinics

            loaded_pending = data.get("pending_doctors", {})
            if isinstance(loaded_pending, dict):
                s.pending_doctors.clear()
                s.pending_doctors.update(loaded_pending)

            users_list = data.get("users", [])
            s.users.clear()
            s.users.update(users_list)

            s.users_info.clear()
            s.users_info.update(data.get("users_info", {}))

            if "admins" in data and isinstance(data["admins"], list):
                s.admins.clear()
                s.admins.update(data["admins"])

            s.admin_history[:] = data.get("admin_history", s.admin_history)

            s.diagnosis_requests.clear()
            s.diagnosis_requests.update(data.get("diagnosis_requests", {}))

            s.appointments.clear()
            appts_raw = data.get("appointments", {})
            for k, v in appts_raw.items():
                copy = v.copy()
                dt_iso = copy.get("datetime_iso")
                if dt_iso:
                    try:
                        dt = s.datetime.fromisoformat(dt_iso)
                        if dt.tzinfo is None:
                            dt = s.tz.localize(dt)
                        copy["datetime"] = dt
                    except Exception:
                        copy["datetime"] = None
                else:
                    copy["datetime"] = None

                doc_id = copy.get("doctor_id")
                clinic_id = copy.get("clinic_id")
                if clinic_id:
                    clinic = next((x for x in s.clinics if x["id"] == clinic_id), None)
                    if clinic:
                        copy["clinic"] = clinic
                        if doc_id:
                            doc = next((d for d in clinic["doctors"] if d["id"] == doc_id), None)
                            copy["doctor_obj"] = doc
                s.appointments[k] = copy

            s.logger.info("Loaded persistent data from %s", s.DATA_FILE)
            s.data_loaded_successfully = True
        except Exception as e:
            s.logger.error("CRITICAL: load_data failed: %s", e)
            s.logger.error("Stopping bot to prevent data loss. Please check your JSON file.")
            s.data_loaded_successfully = False
            sys.exit(1)


def save_data():
    with s.data_lock:
        if not s.data_loaded_successfully:
            s.logger.warning("Data was not loaded successfully. Skipping save to prevent data loss.")
            return
        try:
            clinics_snapshot = copy_module.deepcopy(s.clinics)
            pending_snapshot = copy_module.deepcopy(s.pending_doctors)
            users_snapshot = list(s.users)
            users_info_snapshot = copy_module.deepcopy(s.users_info)
            admins_snapshot = list(s.admins)
            admin_history_snapshot = copy_module.deepcopy(s.admin_history)
            diagnosis_snapshot = copy_module.deepcopy(s.diagnosis_requests)
            appointments_snapshot = copy_module.deepcopy(list(s.appointments.items()))

            to_save = {
                "clinics": clinics_snapshot,
                "pending_doctors": pending_snapshot,
                "appointments": {},
                "users": users_snapshot,
                "users_info": users_info_snapshot,
                "admins": admins_snapshot,
                "admin_history": admin_history_snapshot,
                "diagnosis_requests": diagnosis_snapshot,
            }
            for k, v in appointments_snapshot:
                copy = v.copy()
                dt = copy.pop("datetime", None)
                if isinstance(dt, s.datetime):
                    if dt.tzinfo is None:
                        dt = s.tz.localize(dt)
                    copy["datetime_iso"] = dt.isoformat()
                else:
                    copy["datetime_iso"] = None

                doc = copy.get("doctor_obj")
                if doc:
                    copy["doctor_id"] = doc.get("id")
                    for c in clinics_snapshot:
                        if any(d.get("id") == doc.get("id") for d in c["doctors"]):
                            copy["clinic_id"] = c["id"]
                            break
                clinic = copy.get("clinic")
                if clinic and "clinic_id" not in copy:
                    copy["clinic_id"] = clinic.get("id")
                copy.pop("doctor_obj", None)
                copy.pop("clinic", None)
                to_save["appointments"][k] = copy

            temp_file = f"{s.DATA_FILE}.{s.os.getpid()}.{s.threading.get_ident()}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                s.json.dump(to_save, f, ensure_ascii=False, indent=2)

            s.os.replace(temp_file, s.DATA_FILE)

            s.logger.debug("Saved data to %s", s.DATA_FILE)
        except Exception:
            s.logger.exception("save_data failed")
