from datetime import timedelta, timezone
from pathlib import Path

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

from config import Config


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Сначала войдите в систему.'
login_manager.login_message_category = 'warning'


MSK_OFFSET = timedelta(hours=3)

def to_moscow_time(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value + MSK_OFFSET



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    instance_path = Path(app.root_path).parent / 'instance'
    instance_path.mkdir(exist_ok=True)
    Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    @app.template_filter('msk_datetime')
    def msk_datetime(value, fmt='%d.%m.%Y %H:%M'):
        converted = to_moscow_time(value)
        return converted.strftime(fmt) if converted else ''

    @app.context_processor
    def inject_helpers():
        return {'format_msk_datetime': msk_datetime}


    from .routes import register_routes
    register_routes(app)

    with app.app_context():
        from .models import Role, User, Category

        db.create_all()
        seed_data(Role, User, Category)

    return app


def seed_data(Role, User, Category):
    default_roles = [
        ('admin', 'Администратор системы'),
        ('teacher', 'Преподаватель'),
        ('student', 'Студент'),
    ]

    for role_name, description in default_roles:
        if not Role.query.filter_by(name=role_name).first():
            db.session.add(Role(name=role_name, description=description))
    db.session.commit()
    admin_role = Role.query.filter_by(name='admin').first()
    if admin_role and not User.query.filter_by(username='admin').first():
        admin = User(username='admin', full_name='Администратор', role=admin_role)
        admin.set_password('admin123')
        db.session.add(admin)

    if not Category.query.first():
        categories = [
            Category(name='Лекции', description='Лекционные материалы'),
            Category(name='Лабораторные работы', description='Материалы для лабораторных работ'),
            Category(name='Методические указания', description='Методические материалы'),
        ]
        db.session.add_all(categories)

    db.session.commit()