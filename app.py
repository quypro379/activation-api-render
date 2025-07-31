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

        now = datetime.now(pytz.UTC)
        expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)
        
        # Thêm log để debug
        logger.debug(f"Thời gian hiện tại: {now}, Thời gian hết hạn: {expires_at}")
        
        if expires_at < now:
            logger.warning(f"License hết hạn: {expires_at} < {now}")
            return jsonify({
                "success": False,
                "error": "License đã hết hạn",
                "expired": True,  # Thêm trường này để client biết là do hết hạn
                "server_time": now.isoformat(),
                "expires_at": license_data['expires_at']
            }), 403

        return jsonify({
            "success": True,
            "valid": True,
            "license_type": license_data.get('license_type', 'standard'),
            "expires_at": license_data['expires_at'],
            "activated_at": license_data['activated_at'],
            "server_time": now.isoformat()  # Trả về thời gian server để client so sánh
        }), 200

    except Exception as e:
        logger.error(f"Lỗi verify: {str(e)}", exc_info=True)
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

        now = datetime.now(pytz.UTC)
        expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)
        
        # Thêm log để debug
        logger.debug(f"Thời gian hiện tại: {now}, Thời gian hết hạn: {expires_at}")
        
        if expires_at < now:
            logger.warning(f"License hết hạn: {expires_at} < {now}")
            return jsonify({
                "success": False,
                "error": "License đã hết hạn",
                "expired": True,  # Thêm trường này để client biết là do hết hạn
                "server_time": now.isoformat(),
                "expires_at": license_data['expires_at']
            }), 403

        return jsonify({
            "success": True,
            "valid": True,
            "license_type": license_data.get('license_type', 'standard'),
            "expires_at": license_data['expires_at'],
            "activated_at": license_data['activated_at'],
            "server_time": now.isoformat()  # Trả về thời gian server để client so sánh
        }), 200

    except Exception as e:
        logger.error(f"Lỗi verify: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Lỗi hệ thống"}), 500
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
