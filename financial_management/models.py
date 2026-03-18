from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    monthly_limit = db.Column(db.Float, default=0.0)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    budget = db.Column(db.Float, default=0.0)  # Az új mező a projekt keretnek
    items = db.relationship('TransactionItem', backref='project', lazy=True)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

# Címke kapcsolótábla
item_tags = db.Table('item_tags',
    db.Column('item_id', db.Integer, db.ForeignKey('transaction_item.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)


# Felhasználó modell
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    default_wallet_id = db.Column(db.Integer) # Gyorsításhoz

# Pénznemek (HUF, EUR, stb.)
class Currency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(3), unique=True, nullable=False)
    symbol = db.Column(db.String(5))

# Zsebek (Készpénz, Bankkártya)
class Wallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    currency_id = db.Column(db.Integer, db.ForeignKey('currency.id'))

# Helyszínek alapértelmezett értékekkel
class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    default_category_id = db.Column(db.Integer)
    default_currency_id = db.Column(db.Integer)

# Tranzakció FEJLÉC
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallet.id'))
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    total_amount = db.Column(db.Float, nullable=False)
    attachment_path = db.Column(db.String(255)) # Fájl elérése
    type = db.Column(db.String(20), default='expense') # 'expense', 'income', 'transfer'
    to_wallet_id = db.Column(db.Integer, db.ForeignKey('wallet.id'), nullable=True)
    # Kapcsolat a tételekkel (cascade törlés: ha törlöd a tranzakciót, törlődnek a tételek is)
    items = db.relationship('TransactionItem', backref='parent', cascade="all, delete-orphan")
    # Kapcsolatok a könnyű eléréshez (Relationship-ek)
    user = db.relationship('User', backref='transactions')
    wallet = db.relationship('Wallet', foreign_keys=[wallet_id], backref='transactions_out')
    to_wallet = db.relationship('Wallet', foreign_keys=[to_wallet_id], backref='transactions_in')    
    location = db.relationship('Location', backref='transactions') # EZ KELL AZ ISMERETLEN HELY ELLEN

class TransactionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'))
    amount = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id')) # Most már van hová mutatni!
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    description = db.Column(db.String(200))

    category = db.relationship('Category', backref='items')
    
    # Címkék kapcsolata
    tags = db.relationship('Tag', secondary=item_tags, backref=db.backref('items', lazy='dynamic'))

