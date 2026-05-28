import os, zipfile, tempfile
from flask import Blueprint, send_file
from flask_login import login_required, current_user

dl_bp = Blueprint('dl', __name__)

@dl_bp.route('/admin/download-data')
@login_required
def download_data():
    if not current_user.is_admin:
        return 'Forbidden', 403
    tmp = tempfile.mktemp(suffix='.zip')
    with zipfile.ZipFile(tmp, 'w') as z:
        data_dir = '/data'
        for f in os.listdir(data_dir):
            full = os.path.join(data_dir, f)
            if os.path.isfile(full):
                z.write(full, f)
    return send_file(tmp, as_attachment=True, download_name='render_data.zip')
