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

        # Validate input
        # Validate input
        if not key:
            return jsonify({"success": False, "error": "Thiếu mã kích hoạt"}), 400

            
        if not hardware_id:
            return jsonify({"success": False, "error": "Thiếu hardware_id"}), 400

        doc_ref, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"success": False, "error": "Mã kích hoạt không tồn tại"}), 404

        now = datetime.now(pytz.UTC)
        
        # License đã kích hoạt trước đó
        if license_data.get('activated_at'):
            if license_data['hardware_id'] != hardware_id:
                return jsonify({"success": False, "error": "Mã này đã được kích hoạt trên máy khác"}), 403
            else:
                # Cho phép tái tạo license file nếu máy trùng
                return jsonify({
                    "success": True,
                    "license_type": license_data.get('license_type', 'standard'),
                    "expires_at": license_data['expires_at'],
                    "activated_at": license_data['activated_at'],
                    "message": "Đã kích hoạt trước đó"
                }), 200


        # Kích hoạt mới
# Xử lý expires_at dựa trên loại license
        if license_data.get('license_type') == 'lifetime':
            expires_at = datetime.fromisoformat(license_data['expires_at'])
        else:
            try:
                duration_days = int(license_data.get('duration_days', 30))  # mặc định 30 ngày nếu thiếu
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
    """Endpoint kiểm tra license định kỳ"""
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

        # Kiểm tra trạng thái kích hoạt
        if not license_data.get('activated_at'):
            return jsonify({"success": False, "error": "License chưa được kích hoạt"}), 403

        # Kiểm tra hardware_id
        if license_data.get('hardware_id') != hardware_id:
            return jsonify({"success": False, "error": "Key đã được sử dụng trên thiết bị khác"}), 403

        # Sử dụng múi giờ Việt Nam (UTC+7)
        tz = pytz.timezone("Asia/Ho_Chi_Minh")
        now = datetime.now(tz)
        
        # Đảm bảo expires_at được chuyển đổi sang UTC+7
        expires_at = datetime.fromisoformat(license_data['expires_at'])
        if expires_at.tzinfo is None:
            expires_at = tz.localize(expires_at)
        else:
            expires_at = expires_at.astimezone(tz)
        
        response_data = {
            "success": True,
            "valid": expires_at > now,
            "license_type": license_data.get('license_type', 'standard'),
            "expires_at": expires_at.isoformat(),
            "activated_at": license_data['activated_at']
        }

        if expires_at < now:
            return jsonify({
                **response_data,
                "success": False,
                "error": "License đã hết hạn"
            }), 403

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Lỗi verify: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Lỗi hệ thống"}), 500
@app.route('/time', methods=['GET'])
def get_server_time():
    """
    Trả về giờ hiện tại của server (múi giờ Việt Nam).
    Client dùng để xác minh thời gian thực.
    """
    try:
        now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh"))
        return jsonify({
            "success": True,
            "server_time": now.isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Lỗi khi trả về giờ server: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Không lấy được giờ server"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
