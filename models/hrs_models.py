# ═══════════════════════════════════════════════════════════════
#  HRS — Human Resources System
#
# ═══════════════════════════════════════════════════════════════

class HRSDepartment(Base):
    """"""
    __tablename__ = 'hrs_departments'
    id          = Column(Integer, primary_key=True)
    name        = Column(String(200), nullable=False)
    name_en     = Column(String(200))
    code        = Column(String(50), unique=True, nullable=True)   #
    parent_id   = Column(Integer, ForeignKey('hrs_departments.id'), nullable=True)  #
    manager_id  = Column(Integer, ForeignKey('hrs_employees.id'), nullable=True)    #
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.now)
    parent      = relationship('HRSDepartment', remote_side='HRSDepartment.id', foreign_keys=[parent_id])
    employees   = relationship('HRSEmployee', back_populates='department',
                               foreign_keys='HRSEmployee.department_id')


class HRSPosition(Base):
    """"""
    __tablename__ = 'hrs_positions'
    id              = Column(Integer, primary_key=True)
    name            = Column(String(200), nullable=False)
    name_en         = Column(String(200))
    department_id   = Column(Integer, ForeignKey('hrs_departments.id'), nullable=True)
    grade           = Column(String(50))   #
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)
    department      = relationship('HRSDepartment', foreign_keys=[department_id])
    employees       = relationship('HRSEmployee', back_populates='position')


class HRSEmployee(Base):
    """"""
    __tablename__ = 'hrs_employees'

    id              = Column(Integer, primary_key=True)
    #
    user_id         = Column(Integer, ForeignKey('users.id'), nullable=True, unique=True)

    #
    employee_number = Column(String(50), unique=True, nullable=False)  #
    full_name       = Column(String(200), nullable=False)
    full_name_en    = Column(String(200))
    national_id     = Column(String(50))                #
    nationality     = Column(String(100))               #
    birth_date      = Column(Date)
    gender          = Column(String(10))                # male / female
    marital_status  = Column(String(20))                # single/married/divorced/widowed
    religion        = Column(String(50))
    photo_b64       = Column(Text)                      #

    #
    department_id   = Column(Integer, ForeignKey('hrs_departments.id'), nullable=True, index=True)
    position_id     = Column(Integer, ForeignKey('hrs_positions.id'), nullable=True)
    direct_manager_id = Column(Integer, ForeignKey('hrs_employees.id'), nullable=True)  #
    employment_type = Column(String(30), default='full_time')  # full_time/part_time/contract/intern
    hire_date       = Column(Date)                      #
    probation_end   = Column(Date)                      #
    contract_end    = Column(Date)                      #
    work_location   = Column(String(200))               #
    work_email      = Column(String(200))
    work_phone      = Column(String(50))
    extension       = Column(String(20))                #

    #
    personal_email  = Column(String(200))
    personal_phone  = Column(String(50))
    address         = Column(Text)
    emergency_contact_name  = Column(String(200))
    emergency_contact_phone = Column(String(50))
    emergency_contact_rel   = Column(String(100))       #

    #
    status          = Column(String(20), default='active', index=True)
    # active / on_leave / suspended / terminated / resigned
    termination_date    = Column(Date)
    termination_reason  = Column(Text)

    is_active       = Column(Boolean, default=True)
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)
    updated_at      = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    #
    user            = relationship('User', foreign_keys=[user_id])
    department      = relationship('HRSDepartment', back_populates='employees',
                                   foreign_keys=[department_id])
    position        = relationship('HRSPosition', back_populates='employees')
    direct_manager  = relationship('HRSEmployee', remote_side='HRSEmployee.id',
                                   foreign_keys=[direct_manager_id])
    education       = relationship('HRSEducation', back_populates='employee',
                                   cascade='all, delete-orphan')
    salary          = relationship('HRSSalary', back_populates='employee', uselist=False)
    leave_balances  = relationship('HRSLeaveBalance', back_populates='employee',
                                   cascade='all, delete-orphan')
    leave_requests  = relationship('HRSLeaveRequest', back_populates='employee',
                                   foreign_keys='HRSLeaveRequest.employee_id',
                                   cascade='all, delete-orphan')


class HRSEducation(Base):
    """"""
    __tablename__ = 'hrs_education'
    id              = Column(Integer, primary_key=True)
    employee_id     = Column(Integer, ForeignKey('hrs_employees.id'), nullable=False, index=True)
    degree          = Column(String(100), nullable=False)
    #
    major           = Column(String(200))               #
    institution     = Column(String(300))               #
    country         = Column(String(100))               #
    graduation_year = Column(Integer)
    grade           = Column(String(50))                #
    attachment_b64  = Column(Text)                      #
    attachment_name = Column(String(255))
    is_primary      = Column(Boolean, default=False)    #
    created_at      = Column(DateTime, default=datetime.now)
    employee        = relationship('HRSEmployee', back_populates='education')


class HRSLeaveType(Base):
    """"""
    __tablename__ = 'hrs_leave_types'
    id              = Column(Integer, primary_key=True)
    name            = Column(String(200), nullable=False)
    name_en         = Column(String(200))
    code            = Column(String(30), unique=True)   #
    days_per_year   = Column(Integer, default=0)        #
    is_paid         = Column(Boolean, default=True)     #
    requires_attachment = Column(Boolean, default=False) #
    min_days        = Column(Integer, default=1)        #
    max_days        = Column(Integer, default=0)        #
    gender_specific = Column(String(10), default='all') # all / male / female
    color           = Column(String(20), default='#0C67EC')
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)
    balances        = relationship('HRSLeaveBalance', back_populates='leave_type')
    requests        = relationship('HRSLeaveRequest', back_populates='leave_type')


class HRSLeaveBalance(Base):
    """"""
    __tablename__ = 'hrs_leave_balances'
    __table_args__ = (UniqueConstraint('employee_id', 'leave_type_id', 'year',
                                       name='uq_hrs_leave_balance'),)
    id              = Column(Integer, primary_key=True)
    employee_id     = Column(Integer, ForeignKey('hrs_employees.id'), nullable=False, index=True)
    leave_type_id   = Column(Integer, ForeignKey('hrs_leave_types.id'), nullable=False)
    year            = Column(Integer, nullable=False)   #
    entitled_days   = Column(Integer, default=0)        #
    used_days       = Column(Integer, default=0)        #
    carried_over    = Column(Integer, default=0)        #
    created_at      = Column(DateTime, default=datetime.now)
    updated_at      = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    employee        = relationship('HRSEmployee', back_populates='leave_balances')
    leave_type      = relationship('HRSLeaveType', back_populates='balances')

    @property
    def remaining_days(self):
        return (self.entitled_days + self.carried_over) - self.used_days


class HRSApprovalStep(Base):
    """"""
    __tablename__ = 'hrs_approval_steps'
    id              = Column(Integer, primary_key=True)
    department_id   = Column(Integer, ForeignKey('hrs_departments.id'), nullable=True)
    #
    leave_type_id   = Column(Integer, ForeignKey('hrs_leave_types.id'), nullable=True)
    #
    step_order      = Column(Integer, nullable=False, default=1)  #
    step_role       = Column(String(50))
    # direct_manager / department_manager / hr_manager / ceo / specific_user
    approver_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    #
    step_label      = Column(String(200))      #
    step_label_en   = Column(String(200))
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)
    department      = relationship('HRSDepartment', foreign_keys=[department_id])
    leave_type      = relationship('HRSLeaveType', foreign_keys=[leave_type_id])
    approver_user   = relationship('User', foreign_keys=[approver_user_id])


class HRSLeaveRequest(Base):
    """"""
    __tablename__ = 'hrs_leave_requests'
    id              = Column(Integer, primary_key=True)
    request_number  = Column(String(50), unique=True, nullable=False)
    employee_id     = Column(Integer, ForeignKey('hrs_employees.id'), nullable=False, index=True)
    leave_type_id   = Column(Integer, ForeignKey('hrs_leave_types.id'), nullable=False)
    from_date       = Column(Date, nullable=False)
    to_date         = Column(Date, nullable=False)
    total_days      = Column(Integer, default=1)
    reason          = Column(Text)
    attachment_b64  = Column(Text)
    attachment_name = Column(String(255))
    delegate_id     = Column(Integer, ForeignKey('hrs_employees.id'), nullable=True)
    #

    status          = Column(String(20), default='pending', index=True)
    # pending / approved / rejected / cancelled

    current_step    = Column(Integer, default=1)        #
    rejection_reason = Column(Text)

    created_at      = Column(DateTime, default=datetime.now)
    updated_at      = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    employee        = relationship('HRSEmployee', back_populates='leave_requests',
                                   foreign_keys=[employee_id])
    leave_type      = relationship('HRSLeaveType', back_populates='requests')
    delegate        = relationship('HRSEmployee', foreign_keys=[delegate_id])
    approvals       = relationship('HRSLeaveApproval', back_populates='request',
                                   cascade='all, delete-orphan', order_by='HRSLeaveApproval.step_order')


class HRSLeaveApproval(Base):
    """"""
    __tablename__ = 'hrs_leave_approvals'
    id              = Column(Integer, primary_key=True)
    request_id      = Column(Integer, ForeignKey('hrs_leave_requests.id'), nullable=False)
    step_order      = Column(Integer, nullable=False)
    approver_id     = Column(Integer, ForeignKey('users.id'), nullable=False)
    status          = Column(String(20))               # approved / rejected / pending
    comments        = Column(Text)
    action_at       = Column(DateTime)
    created_at      = Column(DateTime, default=datetime.now)
    request         = relationship('HRSLeaveRequest', back_populates='approvals')
    approver        = relationship('User', foreign_keys=[approver_id])


class HRSSalary(Base):
    """"""
    __tablename__ = 'hrs_salaries'
    id              = Column(Integer, primary_key=True)
    employee_id     = Column(Integer, ForeignKey('hrs_employees.id'), nullable=False,
                             unique=True)
    currency        = Column(String(10), default='JOD')
    basic_salary    = Column(Integer, default=0)        #
    housing_allowance   = Column(Integer, default=0)    #
    transport_allowance = Column(Integer, default=0)    #
    food_allowance      = Column(Integer, default=0)    #
    phone_allowance     = Column(Integer, default=0)    #
    other_allowances    = Column(Integer, default=0)    #
    social_security     = Column(Integer, default=0)    #
    income_tax          = Column(Integer, default=0)    #
    other_deductions    = Column(Integer, default=0)    #
    bank_name       = Column(String(200))
    bank_account    = Column(String(100))
    iban            = Column(String(50))
    effective_date  = Column(Date)                      #
    notes           = Column(Text)
    updated_at      = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by      = Column(Integer, ForeignKey('users.id'), nullable=True)
    employee        = relationship('HRSEmployee', back_populates='salary')
    updater         = relationship('User', foreign_keys=[updated_by])

    @property
    def gross_salary(self):
        return (self.basic_salary + self.housing_allowance + self.transport_allowance +
                self.food_allowance + self.phone_allowance + self.other_allowances)

    @property
    def total_deductions(self):
        return self.social_security + self.income_tax + self.other_deductions

    @property
    def net_salary(self):
        return self.gross_salary - self.total_deductions


class HRSSalarySlip(Base):
    """"""
    __tablename__ = 'hrs_salary_slips'
    __table_args__ = (UniqueConstraint('employee_id', 'month', 'year',
                                       name='uq_hrs_salary_slip'),)
    id              = Column(Integer, primary_key=True)
    employee_id     = Column(Integer, ForeignKey('hrs_employees.id'), nullable=False, index=True)
    month           = Column(Integer, nullable=False)   # 1-12
    year            = Column(Integer, nullable=False)
    #
    basic_salary        = Column(Integer, default=0)
    housing_allowance   = Column(Integer, default=0)
    transport_allowance = Column(Integer, default=0)
    food_allowance      = Column(Integer, default=0)
    phone_allowance     = Column(Integer, default=0)
    other_allowances    = Column(Integer, default=0)
    overtime_amount     = Column(Integer, default=0)    #
    overtime_hours      = Column(Integer, default=0)    #
    #
    social_security     = Column(Integer, default=0)
    income_tax          = Column(Integer, default=0)
    other_deductions    = Column(Integer, default=0)
    leave_deductions    = Column(Integer, default=0)    #
    #
    notes           = Column(Text)
    status          = Column(String(20), default='draft')   # draft / issued / paid
    issued_at       = Column(DateTime)
    issued_by       = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at      = Column(DateTime, default=datetime.now)
    employee        = relationship('HRSEmployee', foreign_keys=[employee_id])
    issuer          = relationship('User', foreign_keys=[issued_by])

    @property
    def gross_salary(self):
        return (self.basic_salary + self.housing_allowance + self.transport_allowance +
                self.food_allowance + self.phone_allowance + self.other_allowances +
                self.overtime_amount)

    @property
    def total_deductions(self):
        return (self.social_security + self.income_tax +
                self.other_deductions + self.leave_deductions)

    @property
    def net_salary(self):
        return self.gross_salary - self.total_deductions
