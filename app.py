from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
import re

# Thiết lập Flask và CORS
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
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Hàm kiểm tra key hợp lệ
def is_valid_key(key: str) -> bool:
    return bool(re.match(r'^[A-Z0-9]{8}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{12}$', key))

# Hàm kiểm tra hardware_id hợp lệ
def is_valid_hardware_id(hwid: str) -> bool:
    return len(hwid) == 64 and hwid.isalnum()

# Hàm tiện ích định dạng thời gian
def format_datetime(dt: datetime) -> str:
    return dt.astimezone(VN_TZ).strftime("%d/%m/%Y %H:%M:%S")

# Hàm lấy document license với kiểm tra bảo mật
def get_license_doc(key: str):
    if not is_valid_key(key):
        return None, None
    doc_ref = db.collection('licenses').document(key)
    doc = doc_ref.get()
    return doc_ref, doc.to_dict() if doc.exists else None

@app.route('/wakeup', methods=['GET'])
def wakeup():
    return jsonify({"status": "active", "time": format_datetime(datetime.now(VN_TZ)}), 200

@app.route('/activate', methods=['POST'])
@cross_origin()
def activate_key():
    try:
        data = request.json
        logger.debug(f"Activate request: {data}")

        key = data.get('key', '').strip()
        hardware_id = data.get('hardware_id', '').strip()

        # Kiểm tra dữ liệu đầu vào
        if not is_valid_key(key):
            return jsonify({"success": False, "error": "Mã kích hoạt không hợp lệ"}), 400
            
        if not is_valid_hardware_id(hardware_id):
            return jsonify({"success": False, "error": "Hardware ID không hợp lệ"}), 400

        doc_ref, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"success": False, "error": "Mã kích hoạt không tồn tại"}), 404

        now = datetime.now(VN_TZ)

        # Kiểm tra trạng thái license
        if license_data.get('activated_at'):
            if license_data['hardware_id'] != hardware_id:
                logger.warning(f"Attempt to reuse key {key} on different hardware")
                return jsonify({
                    "success": False, 
                    "error": "Mã này đã được kích hoạt trên máy khác",
                    "original_hardware_id": license_data['hardware_id'][:8] + "..."
                }), 403

            expires_at = datetime.fromisoformat(license_data['expires_at']).astimezone(VN_TZ)
            return jsonify({
                "success": True,
                "license_type": license_data.get('license_type', 'standard'),
                "expires_at": expires_at.isoformat(),
                "activated_at": license_data['activated_at'],
                "expires_at_display": format_datetime(expires_at),
                "activated_at_display": format_datetime(datetime.fromisoformat(license_data['activated_at']).astimezone(VN_TZ)),
                "message": "Đã kích hoạt trước đó"
            }), 200

        # Xử lý kích hoạt mới
        license_type = license_data.get('license_type', 'standard')
        
        if license_type == 'lifetime':
            expires_at = datetime.fromisoformat(license_data['expires_at']).astimezone(VN_TZ)
        else:
            try:
                duration_days = int(license_data.get('duration_days', 30))
            except ValueError:
                duration_days = 30
            expires_at = now + timedelta(days=duration_days)

        update_data = {
            'hardware_id': hardware_id,
            'activated_at': now.isoformat(),
            'expires_at': expires_at.isoformat(),
            'last_check': now.isoformat(),
            'activation_count': firestore.Increment(1)
        }
        
        doc_ref.update(update_data)
        logger.info(f"Kích hoạt thành công: {key} cho hardware_id: {hardware_id[:8]}...")

        return jsonify({
            "success": True,
            "license_type": license_type,
            "expires_at": expires_at.isoformat(),
            "activated_at": now.isoformat(),
            "expires_at_display": format_datetime(expires_at),
            "activated_at_display": format_datetime(now),
            "hardware_id": hardware_id[:8] + "..."  # Chỉ trả về một phần để bảo mật
        }), 200

    except Exception as e:
        logger.error(f"Lỗi activate: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Lỗi hệ thống"}), 500

@app.route('/verify', methods=['POST'])
@cross_origin()
def verify_key():
    try:
        data = request.json
        logger.debug(f"Verify request: {data}")

        key = data.get('key', '').strip()
        hardware_id = data.get('hardware_id', '').strip()

        if not is_valid_key(key) or not is_valid_hardware_id(hardware_id):
            return jsonify({"success": False, "error": "Thông tin không hợp lệ"}), 400

        _, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"success": False, "error": "Key không hợp lệ"}), 404

        if not license_data.get('activated_at'):
            return jsonify({"success": False, "error": "License chưa được kích hoạt"}), 403

        if license_data.get('hardware_id') != hardware_id:
            logger.warning(f"Hardware ID mismatch for key {key}")
            return jsonify({
                "success": False, 
                "error": "Key đã được sử dụng trên thiết bị khác",
                "original_hardware": license_data['hardware_id'][:8] + "..."
            }), 403

        now = datetime.now(VN_TZ)
        expires_at = datetime.fromisoformat(license_data['expires_at']).astimezone(VN_TZ)

        # Cập nhật thời gian kiểm tra cuối cùng
        db.collection('licenses').document(key).update({
            'last_check': now.isoformat(),
            'check_count': firestore.Increment(1)
        })

        if expires_at < now:
            return jsonify({
                "success": False, 
                "error": "License đã hết hạn",
                "expired_since": format_datetime(expires_at)
            }), 403

        return jsonify({
            "success": True,
            "valid": True,
            "license_type": license_data.get('license_type', 'standard'),
            "expires_at": expires_at.isoformat(),
            "activated_at": license_data['activated_at'],
            "expires_at_display": format_datetime(expires_at),
            "activated_at_display": format_datetime(datetime.fromisoformat(license_data['activated_at']).astimezone(VN_TZ)),
            "remaining_days": (expires_at - now).days
        }), 200

    except Exception as e:
        logger.error(f"Lỗi verify: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Lỗi hệ thống"}), 500

@app.route('/time', methods=['GET'])
def get_server_time():
    try:
        now = datetime.now(VN_TZ)
        return jsonify({
            "success": True,
            "server_time": now.isoformat(),
            "server_time_display": format_datetime(now),
            "timezone": "Asia/Ho_Chi_Minh (UTC+7)"
        }), 200
    except Exception as e:
        logger.error(f"Lỗi khi trả về giờ server: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Không lấy được giờ server"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
