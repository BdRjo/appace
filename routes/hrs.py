"""
HRS — Human Resources System
routes/hrs.py
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from datetime import date, datetime
import json

hrs_bp = Blueprint('hrs', __name__, url_prefix='/hrs')

# Helper────────────────────────────────────────────────────────────────────
def _t(ar, en=''):
    return en if session.get('lang') == 'en' else ar

def _db():
    return g.db

def _require_hr():
    """Check HR permissions"""
    from utils.helpers import get_permissions
    perms = get_permissions()
    # ...
    if hasattr(current_user, 'role_ref') and current_user.role_ref:
        role_name = (current_user.role_ref.name or '').lower()
        if role_name in ('admin', 'hr', 'superadmin'):
            return True
    return False

# ...
@hrs_bp.route('/employees')
@login_required
def employees():
    from models.hrs_models import HRSEmployee, HRSDepartment, HRSPosition
    db = _db()

    # Filters
    q          = request.args.get('q', '').strip()
    dept_id    = request.args.get('dept_id', '', type=int) or None
    status_f   = request.args.get('status', '')
    emp_type_f = request.args.get('emp_type', '')
    page       = request.args.get('page', 1, type=int)
    per_page   = 20

    query = db.query(HRSEmployee)

    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            HRSEmployee.full_name.ilike(like),
            HRSEmployee.full_name_en.ilike(like),
            HRSEmployee.employee_number.ilike(like),
            HRSEmployee.work_email.ilike(like),
            HRSEmployee.national_id.ilike(like),
        ))
    if dept_id:
        query = query.filter(HRSEmployee.department_id == dept_id)
    if status_f:
        query = query.filter(HRSEmployee.status == status_f)
    if emp_type_f:
        query = query.filter(HRSEmployee.employment_type == emp_type_f)

    total = query.count()
    employees_list = (query
                      .order_by(HRSEmployee.full_name)
                      .offset((page - 1) * per_page)
                      .limit(per_page)
                      .all())

    departments = db.query(HRSDepartment).filter_by(is_active=True).order_by(HRSDepartment.name).all()
    total_pages = (total + per_page - 1) // per_page

    # ...
    stats = {
        'total':      db.query(HRSEmployee).filter_by(is_active=True).count(),
        'active':     db.query(HRSEmployee).filter_by(status='active').count(),
        'on_leave':   db.query(HRSEmployee).filter_by(status='on_leave').count(),
        'terminated': db.query(HRSEmployee).filter_by(status='terminated').count(),
    }

    return render_template('hrs/employees.html',
        employees=employees_list,
        departments=departments,
        stats=stats,
        total=total,
        page=page,
        total_pages=total_pages,
        q=q,
        dept_id=dept_id,
        status_f=status_f,
        emp_type_f=emp_type_f,
    )

# ...
@hrs_bp.route('/employees/new', methods=['GET', 'POST'])
@login_required
def employee_new():
    from models.hrs_models import HRSEmployee, HRSDepartment, HRSPosition, User
    db = _db()

    departments = db.query(HRSDepartment).filter_by(is_active=True).order_by(HRSDepartment.name).all()
    positions   = db.query(HRSPosition).filter_by(is_active=True).order_by(HRSPosition.name).all()
    managers    = db.query(HRSEmployee).filter_by(is_active=True).order_by(HRSEmployee.full_name).all()
    users       = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == 'POST':
        f = request.form

        # Auto-generate employee number
        emp_number = f.get('employee_number', '').strip()
        if not emp_number:
            last = db.query(func.max(HRSEmployee.employee_number)).scalar()
            try:
                emp_number = f'EMP{int(last.replace("EMP",""))+1:04d}'
            except Exception:
                emp_number = f'EMP{db.query(HRSEmployee).count()+1:04d}'

        emp = HRSEmployee(
            employee_number   = emp_number,
            full_name         = f.get('full_name', '').strip(),
            full_name_en      = f.get('full_name_en', '').strip(),
            national_id       = f.get('national_id', '').strip(),
            nationality       = f.get('nationality', '').strip(),
            birth_date        = _parse_date(f.get('birth_date')),
            gender            = f.get('gender', ''),
            marital_status    = f.get('marital_status', ''),
            religion          = f.get('religion', '').strip(),
            department_id     = f.get('department_id') or None,
            position_id       = f.get('position_id') or None,
            direct_manager_id = f.get('direct_manager_id') or None,
            employment_type   = f.get('employment_type', 'full_time'),
            hire_date         = _parse_date(f.get('hire_date')),
            probation_end     = _parse_date(f.get('probation_end')),
            contract_end      = _parse_date(f.get('contract_end')),
            work_location     = f.get('work_location', '').strip(),
            work_email        = f.get('work_email', '').strip(),
            work_phone        = f.get('work_phone', '').strip(),
            extension         = f.get('extension', '').strip(),
            personal_email    = f.get('personal_email', '').strip(),
            personal_phone    = f.get('personal_phone', '').strip(),
            address           = f.get('address', '').strip(),
            emergency_contact_name  = f.get('emergency_contact_name', '').strip(),
            emergency_contact_phone = f.get('emergency_contact_phone', '').strip(),
            emergency_contact_rel   = f.get('emergency_contact_rel', '').strip(),
            user_id           = f.get('user_id') or None,
            notes             = f.get('notes', '').strip(),
            status            = 'active',
            is_active         = True,
        )

        # Employee photo
        photo = request.files.get('photo')
        if photo and photo.filename:
            import base64
            emp.photo_b64 = 'data:' + photo.content_type + ';base64,' + base64.b64encode(photo.read()).decode()

        db.add(emp)
        try:
            db.commit()
            flash(_t('تم إضافة الموظف بنجاح', 'Employee added successfully'), 'success')
            return redirect(url_for('hrs.employee_view', emp_id=emp.id))
        except Exception as e:
            db.rollback()
            from flask import current_app
            current_app.logger.exception(f'HRS new employee error: {e}')
            flash(_t('حدث خطأ، تحقق من البيانات', 'An error occurred'), 'danger')

    return render_template('hrs/employee_form.html',
        emp=None, departments=departments,
        positions=positions, managers=managers, users=users,
        action=_t('إضافة موظف جديد', 'Add New Employee')
    )

# ...
@hrs_bp.route('/employees/<int:emp_id>')
@login_required
def employee_view(emp_id):
    from models.hrs_models import HRSEmployee, HRSEducation, HRSSalary, HRSLeaveBalance, HRSLeaveRequest
    db = _db()
    emp = db.query(HRSEmployee).filter_by(id=emp_id).first()
    if not emp:
        flash(_t('الموظف غير موجود', 'Employee not found'), 'warning')
        return redirect(url_for('hrs.employees'))

    current_year = date.today().year
    leave_balances = (db.query(HRSLeaveBalance)
                      .filter_by(employee_id=emp_id, year=current_year)
                      .all())
    recent_requests = (db.query(HRSLeaveRequest)
                       .filter_by(employee_id=emp_id)
                       .order_by(HRSLeaveRequest.created_at.desc())
                       .limit(5).all())

    return render_template('hrs/employee_view.html',
        emp=emp,
        leave_balances=leave_balances,
        recent_requests=recent_requests,
        current_year=current_year,
    )

# ...
@hrs_bp.route('/employees/<int:emp_id>/edit', methods=['GET', 'POST'])
@login_required
def employee_edit(emp_id):
    from models.hrs_models import HRSEmployee, HRSDepartment, HRSPosition, User
    db = _db()
    emp = db.query(HRSEmployee).filter_by(id=emp_id).first()
    if not emp:
        return redirect(url_for('hrs.employees'))

    departments = db.query(HRSDepartment).filter_by(is_active=True).order_by(HRSDepartment.name).all()
    positions   = db.query(HRSPosition).filter_by(is_active=True).order_by(HRSPosition.name).all()
    managers    = db.query(HRSEmployee).filter(HRSEmployee.id != emp_id, HRSEmployee.is_active == True).order_by(HRSEmployee.full_name).all()
    users       = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == 'POST':
        f = request.form
        emp.full_name         = f.get('full_name', emp.full_name).strip()
        emp.full_name_en      = f.get('full_name_en', emp.full_name_en or '').strip()
        emp.national_id       = f.get('national_id', '').strip()
        emp.nationality       = f.get('nationality', '').strip()
        emp.birth_date        = _parse_date(f.get('birth_date')) or emp.birth_date
        emp.gender            = f.get('gender', emp.gender)
        emp.marital_status    = f.get('marital_status', emp.marital_status)
        emp.religion          = f.get('religion', '').strip()
        emp.department_id     = f.get('department_id') or None
        emp.position_id       = f.get('position_id') or None
        emp.direct_manager_id = f.get('direct_manager_id') or None
        emp.employment_type   = f.get('employment_type', emp.employment_type)
        emp.hire_date         = _parse_date(f.get('hire_date')) or emp.hire_date
        emp.probation_end     = _parse_date(f.get('probation_end'))
        emp.contract_end      = _parse_date(f.get('contract_end'))
        emp.work_location     = f.get('work_location', '').strip()
        emp.work_email        = f.get('work_email', '').strip()
        emp.work_phone        = f.get('work_phone', '').strip()
        emp.extension         = f.get('extension', '').strip()
        emp.personal_email    = f.get('personal_email', '').strip()
        emp.personal_phone    = f.get('personal_phone', '').strip()
        emp.address           = f.get('address', '').strip()
        emp.emergency_contact_name  = f.get('emergency_contact_name', '').strip()
        emp.emergency_contact_phone = f.get('emergency_contact_phone', '').strip()
        emp.emergency_contact_rel   = f.get('emergency_contact_rel', '').strip()
        emp.user_id           = f.get('user_id') or None
        emp.notes             = f.get('notes', '').strip()
        emp.status            = f.get('status', emp.status)
        emp.updated_at        = datetime.now()

        photo = request.files.get('photo')
        if photo and photo.filename:
            import base64
            emp.photo_b64 = 'data:' + photo.content_type + ';base64,' + base64.b64encode(photo.read()).decode()

        try:
            db.commit()
            flash(_t('تم حفظ التعديلات', 'Changes saved'), 'success')
            return redirect(url_for('hrs.employee_view', emp_id=emp.id))
        except Exception as e:
            db.rollback()
            from flask import current_app
            current_app.logger.exception(f'HRS edit employee error: {e}')
            flash(_t('حدث خطأ', 'An error occurred'), 'danger')

    return render_template('hrs/employee_form.html',
        emp=emp, departments=departments,
        positions=positions, managers=managers, users=users,
        action=_t('تعديل بيانات الموظف', 'Edit Employee')
    )

# ...
@hrs_bp.route('/employees/<int:emp_id>/education/save', methods=['POST'])
@login_required
def education_save(emp_id):
    from models.database import HRSEmployee, HRSEducation
    db = _db()
    emp = db.query(HRSEmployee).filter_by(id=emp_id).first()
    if not emp:
        return jsonify({'ok': False}), 404

    f   = request.form
    eid = f.get('edu_id', type=int)

    if eid:
        edu = db.query(HRSEducation).filter_by(id=eid, employee_id=emp_id).first()
        if not edu:
            return jsonify({'ok': False}), 404
    else:
        edu = HRSEducation(employee_id=emp_id)
        db.add(edu)

    edu.degree          = f.get('degree', '').strip()
    edu.major           = f.get('major', '').strip()
    edu.institution     = f.get('institution', '').strip()
    edu.country         = f.get('country', '').strip()
    edu.graduation_year = f.get('graduation_year', type=int)
    edu.grade           = f.get('grade', '').strip()
    edu.is_primary      = bool(f.get('is_primary'))

    att = request.files.get('attachment')
    if att and att.filename:
        import base64
        edu.attachment_b64  = 'data:' + att.content_type + ';base64,' + base64.b64encode(att.read()).decode()
        edu.attachment_name = att.filename

    try:
        db.commit()
        flash(_t('تم حفظ الشهادة', 'Education record saved'), 'success')
    except Exception as e:
        db.rollback()
        from flask import current_app
        current_app.logger.exception(f'HRS education save error: {e}')
        flash(_t('حدث خطأ', 'An error occurred'), 'danger')

    return redirect(url_for('hrs.employee_view', emp_id=emp_id) + '#education')

# ...
@hrs_bp.route('/employees/<int:emp_id>/education/<int:edu_id>/delete', methods=['POST'])
@login_required
def education_delete(emp_id, edu_id):
    from models.database import HRSEducation
    db = _db()
    edu = db.query(HRSEducation).filter_by(id=edu_id, employee_id=emp_id).first()
    if edu:
        db.delete(edu)
        db.commit()
    return redirect(url_for('hrs.employee_view', emp_id=emp_id) + '#education')

# ...
@hrs_bp.route('/employees/<int:emp_id>/salary/save', methods=['POST'])
@login_required
def salary_save(emp_id):
    from models.hrs_models import HRSEmployee, HRSSalary
    db = _db()
    emp = db.query(HRSEmployee).filter_by(id=emp_id).first()
    if not emp:
        return redirect(url_for('hrs.employees'))

    f   = request.form
    sal = emp.salary
    if not sal:
        sal = HRSSalary(employee_id=emp_id)
        db.add(sal)

    def _cents(key):
        try: return int(float(f.get(key, 0)) * 1000)
        except: return 0

    sal.currency            = f.get('currency', 'JOD')
    sal.basic_salary        = _cents('basic_salary')
    sal.housing_allowance   = _cents('housing_allowance')
    sal.transport_allowance = _cents('transport_allowance')
    sal.food_allowance      = _cents('food_allowance')
    sal.phone_allowance     = _cents('phone_allowance')
    sal.other_allowances    = _cents('other_allowances')
    sal.social_security     = _cents('social_security')
    sal.income_tax          = _cents('income_tax')
    sal.other_deductions    = _cents('other_deductions')
    sal.bank_name           = f.get('bank_name', '').strip()
    sal.bank_account        = f.get('bank_account', '').strip()
    sal.iban                = f.get('iban', '').strip()
    sal.effective_date      = _parse_date(f.get('effective_date'))
    sal.notes               = f.get('notes', '').strip()
    sal.updated_by          = current_user.id
    sal.updated_at          = datetime.now()

    try:
        db.commit()
        flash(_t('تم حفظ بيانات الراتب', 'Salary saved'), 'success')
    except Exception as e:
        db.rollback()
        from flask import current_app
        current_app.logger.exception(f'HRS salary save error: {e}')
        flash(_t('حدث خطأ', 'An error occurred'), 'danger')

    return redirect(url_for('hrs.employee_view', emp_id=emp_id) + '#salary')

# ...
@hrs_bp.route('/leave-requests')
@login_required
def leave_requests():
    from models.hrs_models import HRSLeaveRequest, HRSEmployee, HRSLeaveType
    db = _db()

    q        = request.args.get('q', '').strip()
    status_f = request.args.get('status', '')
    dept_id  = request.args.get('dept_id', '', type=int) or None
    page     = request.args.get('page', 1, type=int)
    per_page = 25

    query = db.query(HRSLeaveRequest).join(HRSEmployee)

    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            HRSEmployee.full_name.ilike(like),
            HRSEmployee.employee_number.ilike(like),
            HRSLeaveRequest.request_number.ilike(like),
        ))
    if status_f:
        query = query.filter(HRSLeaveRequest.status == status_f)
    if dept_id:
        query = query.filter(HRSEmployee.department_id == dept_id)

    total = query.count()
    requests_list = (query
                     .order_by(HRSLeaveRequest.created_at.desc())
                     .offset((page - 1) * per_page)
                     .limit(per_page).all())

    from models.hrs_models import HRSDepartment
    departments = db.query(HRSDepartment).filter_by(is_active=True).order_by(HRSDepartment.name).all()
    leave_types = db.query(HRSLeaveType).filter_by(is_active=True).order_by(HRSLeaveType.name).all()

    stats = {
        'pending':  db.query(HRSLeaveRequest).filter_by(status='pending').count(),
        'approved': db.query(HRSLeaveRequest).filter_by(status='approved').count(),
        'rejected': db.query(HRSLeaveRequest).filter_by(status='rejected').count(),
        'total':    db.query(HRSLeaveRequest).count(),
    }

    return render_template('hrs/leave_requests.html',
        requests=requests_list, stats=stats,
        departments=departments, leave_types=leave_types,
        total=total, page=page,
        total_pages=(total + per_page - 1) // per_page,
        q=q, status_f=status_f, dept_id=dept_id,
    )

# ...
@hrs_bp.route('/leave-requests/<int:req_id>/action', methods=['POST'])
@login_required
def leave_request_action(req_id):
    from models.hrs_models import HRSLeaveRequest, HRSLeaveApproval, HRSLeaveBalance
    db = _db()
    req = db.query(HRSLeaveRequest).filter_by(id=req_id).first()
    if not req:
        return jsonify({'ok': False, 'msg': 'Not found'}), 404

    action   = request.form.get('action')   # approve / reject
    comments = request.form.get('comments', '').strip()

    if action not in ('approve', 'reject'):
        return jsonify({'ok': False, 'msg': 'Invalid action'}), 400

    # ...
    approval = HRSLeaveApproval(
        request_id  = req.id,
        step_order  = req.current_step,
        approver_id = current_user.id,
        status      = 'approved' if action == 'approve' else 'rejected',
        comments    = comments,
        action_at   = datetime.now(),
    )
    db.add(approval)

    if action == 'reject':
        req.status           = 'rejected'
        req.rejection_reason = comments
    else:
        # ...
        from models.hrs_models import HRSApprovalStep
        next_step = (db.query(HRSApprovalStep)
                     .filter(
                         HRSApprovalStep.step_order > req.current_step,
                         HRSApprovalStep.is_active == True,
                         or_(HRSApprovalStep.department_id == req.employee.department_id,
                             HRSApprovalStep.department_id == None)
                     )
                     .order_by(HRSApprovalStep.step_order)
                     .first())
        if next_step:
            req.current_step = next_step.step_order
            req.status       = 'pending'
        else:
            req.status = 'approved'
            # ...
            this_year = date.today().year
            bal = (db.query(HRSLeaveBalance)
                   .filter_by(employee_id=req.employee_id,
                              leave_type_id=req.leave_type_id,
                              year=this_year)
                   .first())
            if bal:
                bal.used_days += req.total_days
                bal.updated_at = datetime.now()

    req.updated_at = datetime.now()

    try:
        db.commit()
        return jsonify({'ok': True,
                        'msg': _t('تمت العملية بنجاح', 'Done'),
                        'new_status': req.status})
    except Exception as e:
        db.rollback()
        from flask import current_app
        current_app.logger.exception(f'HRS leave action error: {e}')
        return jsonify({'ok': False, 'msg': str(e)}), 500

# ...
@hrs_bp.route('/departments')
@login_required
def departments():
    from models.hrs_models import HRSDepartment
    db = _db()
    depts = db.query(HRSDepartment).order_by(HRSDepartment.name).all()
    return render_template('hrs/departments.html', departments=depts)

@hrs_bp.route('/departments/save', methods=['POST'])
@login_required
def department_save():
    from models.hrs_models import HRSDepartment
    db = _db()
    f    = request.form
    did  = f.get('dept_id', type=int)

    if did:
        dept = db.query(HRSDepartment).filter_by(id=did).first()
        if not dept:
            return jsonify({'ok': False}), 404
    else:
        dept = HRSDepartment()
        db.add(dept)

    dept.name      = f.get('name', '').strip()
    dept.name_en   = f.get('name_en', '').strip()
    dept.code      = f.get('code', '').strip() or None
    dept.parent_id = f.get('parent_id') or None
    dept.is_active = True

    try:
        db.commit()
        flash(_t('تم الحفظ', 'Saved'), 'success')
    except Exception as e:
        db.rollback()
        from flask import current_app
        current_app.logger.exception(f'HRS dept save error: {e}')
        flash(_t('حدث خطأ', 'Error'), 'danger')

    return redirect(url_for('hrs.departments'))

# ...
@hrs_bp.route('/api/positions')
@login_required
def api_positions():
    from models.hrs_models import HRSPosition
    dept_id = request.args.get('dept_id', type=int)
    db = _db()
    q = db.query(HRSPosition).filter_by(is_active=True)
    if dept_id:
        q = q.filter_by(department_id=dept_id)
    data = [{'id': p.id, 'name': p.name} for p in q.order_by(HRSPosition.name).all()]
    return jsonify(data)

# ...
def _parse_date(val):
    if not val:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except Exception:
            pass
    return None
