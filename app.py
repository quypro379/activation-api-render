from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import pytz
import logging

app = Flask(__name__)
CORS(app)

# Cấu hình logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("LicenseAPI")

# Khởi tạo Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Múi giờ Việt Nam
tz_vn = pytz.timezone("Asia/Ho_Chi_Minh")

def get_license_doc(key):
    """Lấy document license từ Firestore"""
    doc_ref = db.collection('licenses').document(key)
    doc = doc_ref.get()
    return doc_ref, doc.to_dict() if doc.exists else None

@app.route('/wakeup', methods=['GET'])
def wakeup():
    """Endpoint đánh thức server"""
    return jsonify({"status": "active"}), 200

@app.route('/activate', methods=['POST'])
@cross_origin()
def activate_key():
    """Endpoint kích hoạt license"""
    try:
        data = request.json
        logger.debug(f"Activate request: {data}")

        key = data.get('key')
        hardware_id = data.get('hardware_id')

        if not key:
            return jsonify({"success": False, "error": "Thiếu mã kích hoạt"}), 400
        if not hardware_id:
            return jsonify({"success": False, "error": "Thiếu hardware_id"}), 400

        doc_ref, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"success": False, "error": "Mã kích hoạt không tồn tại"}), 404

        now = datetime.now(tz_vn)

        # License đã kích hoạt trước đó
        if license_data.get('activated_at'):
            if license_data['hardware_id'] != hardware_id:
                return jsonify({"success": False, "error": "Mã này đã được kích hoạt trên máy khác"}), 403
            else:
                # Cho phép tái tạo license file nếu máy trùng
                activated_at = datetime.fromisoformat(license_data['activated_at']).astimezone(tz_vn)
                expires_at = datetime.fromisoformat(license_data['expires_at']).astimezone(tz_vn)

                return jsonify({
                    "success": True,
                    "license_type": license_data.get('license_type', 'standard'),
                    "expires_at": expires_at.isoformat(),
                    "activated_at": activated_at.isoformat(),
                    "message": "Đã kích hoạt trước đó"
                }), 200

        # Kích hoạt mới
        if license_data.get('license_type') == 'lifetime':
            expires_at = datetime.fromisoformat(license_data['expires_at']).astimezone(tz_vn)
        else:
            try:
                duration_days = int(license_data.get('duration_days', 30))
            except ValueError:
                duration_days = 30
            expires_at = now + timedelta(days=duration_days)

        update_data = {
            'hardware_id': hardware_id,
            'activated_at': now.isoformat(),
            'expires_at': expires_at.isoformat()
        }
        doc_ref.update(update_data)

        logger.info(f"Kích hoạt thành công: {key}")

        return jsonify({
            "success": True,
            "license_type": license_data.get('license_type', 'standard'),
            "expires_at": expires_at.isoformat(),
            "activated_at": now.isoformat()
        }), 200

    except Exception as e:
        logger.error(f"Lỗi activate: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Lỗi hệ thống"}), 500

@app.route('/verify', methods=['POST'])
@cross_origin()
def verify_key():
    """Endpoint kiểm tra license định kỳ từ client."""
    try:
        data = request.json
        logger.debug(f"Verify request: {data}")

        key = data.get('key')
        hardware_id = data.get('hardware_id')

        if not key or not hardware_id:
            return jsonify({"success": False, "error": "Thiếu thông tin key hoặc hardware_id"}), 400

        _, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"success": False, "error": "Key không hợp lệ"}), 404

        if not license_data.get('activated_at'):
            return jsonify({"success": False, "error": "License chưa được kích hoạt"}), 403

        if license_data.get('hardware_id') != hardware_id:
            return jsonify({"success": False, "error": "Key đã được sử dụng trên thiết bị khác"}), 403

        # ✅ Lấy và chuẩn hóa ngày
        try:
            activated_at = datetime.fromisoformat(license_data['activated_at']).astimezone(tz_vn)
        except Exception as e:
            logger.error(f"Lỗi đọc activated_at: {str(e)}")
            activated_at = None

        try:
            expires_at = datetime.fromisoformat(license_data['expires_at']).astimezone(tz_vn)
        except Exception as e:
            logger.error(f"Lỗi đọc expires_at: {str(e)}")
            expires_at = None

        now = datetime.now(tz_vn)

        # ✅ Nếu hết hạn
        if expires_at and expires_at < now:
            logger.warning(f"Key [{key}] đã hết hạn từ {expires_at.isoformat()}")
            return jsonify({
                "success": False,
                "error": "License đã hết hạn",
                "expires_at": expires_at.isoformat(),
                "activated_at": activated_at.isoformat() if activated_at else "",
                "license_type": license_data.get('license_type', 'standard')
            }), 403

        # ✅ License còn hạn
        return jsonify({
            "success": True,
            "valid": True,
            "license_type": license_data.get('license_type', 'standard'),
            "expires_at": expires_at.isoformat() if expires_at else "",
            "activated_at": activated_at.isoformat() if activated_at else ""
        }), 200

    except Exception as e:
        logger.error(f"Lỗi verify: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Lỗi hệ thống"}), 500


@app.route('/time', methods=['GET'])
def get_server_time():
    """
    Trả về giờ hiện tại của server (múi giờ Việt Nam).
    Bao gồm ISO để client tính toán và chuỗi hiển thị đẹp.
    """
    try:
        now = datetime.now(tz_vn)
        return jsonify({
            "success": True,
            "server_time_iso": now.isoformat(),
            "server_time_display": now.strftime("%H:%M - %d/%m/%Y"),
            "timezone": "+07:00"
        }), 200
    except Exception as e:
        logger.error(f"Lỗi khi trả về giờ server: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Không lấy được giờ server"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

@app.route('/secretkey', methods=['GET'])
def get_service_account_key():
    try:
        with open("/etc/secrets/serviceAccountKey.json", "r", encoding="utf-8") as f:
            content = f.read()
        return app.response_class(content, mimetype='application/json')
    except Exception as e:
        return jsonify({"error": f"Không thể đọc key: {str(e)}"}), 500
@app.route('/upload-license', methods=['POST'])
@cross_origin()
def upload_license():
    try:
        # Lấy dữ liệu từ request body
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Thiếu dữ liệu"}), 400

        # Kiểm tra token
        token = data.get("token")
        if token != "abc123upload":
            return jsonify({"success": False, "error": "Token không hợp lệ"}), 403

        # Lấy các thông tin cần thiết
        key = data.get("key")
        hardware_id = data.get("hardware_id")
        duration_days = data.get("duration_days", 90)

        if not key or not hardware_id:
            return jsonify({"success": False, "error": "Thiếu key hoặc hardware_id"}), 400

        # Tạo license mới
        now = datetime.now(tz_vn)
        expires_at = now + timedelta(days=int(duration_days))

        license_data = {
            "key": key,
            "hardware_id": hardware_id,
            "license_type": "trial",
            "activated_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "created_at": now.isoformat()
        }

        # Lưu vào Firestore
        doc_ref = db.collection("licenses").document(key)
        if doc_ref.get().exists:
            return jsonify({"success": False, "error": "Key đã tồn tại"}), 409

        doc_ref.set(license_data)
        return jsonify({"success": True}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


