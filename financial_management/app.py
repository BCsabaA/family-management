import os
from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, User, Wallet, Currency, Location, Transaction, TransactionItem, Category
from datetime import datetime
from sqlalchemy import func, extract

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fejlesztoi-kulcs-123' # Később változtasd meg!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db.init_app(app)

with app.app_context():
    #db.drop_all() # Mindent letakarítunk
    db.create_all() # Újraépítjük

    if not Currency.query.filter_by(code='HUF').first():
    # 1. Alap adatok
        huf = Currency(code='HUF', symbol='Ft')
        db.session.add(huf)
        db.session.flush()

        kat_elelmiszer = Category(name='Élelmiszer')
        kat_auto = Category(name='Autó/Üzemanyag')
        db.session.add_all([kat_elelmiszer, kat_auto])
        db.session.commit() # Itt fixálódnak az ID-k!

        # 2. Helyszínek az új ID-kkal
        db.session.add(Location(name='Tesco', default_category_id=kat_elelmiszer.id))
        db.session.add(Location(name='Shell kút', default_category_id=kat_auto.id))
    
        # 3. Felhasználó és Zseb
        user = User(username='admin', password_hash='hash')
        db.session.add(user)
        db.session.add(Wallet(name='Bankkártya', currency_id=huf.id))
        db.session.add(Wallet(name='Készpénz', currency_id=huf.id))
    
        db.session.commit()



@app.route('/')
def index():
    # A legutóbbi 10 tranzakció megjelenítése
    transactions = Transaction.query.order_by(Transaction.date.desc()).limit(10).all()
    return render_template('index.html', transactions=transactions)

@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        loc_id_raw = request.form.get('location_id')
        loc_id = int(loc_id_raw) if loc_id_raw and loc_id_raw != "" else None
        # Beolvassuk a dátumot az űrlapról
        date_str = request.form.get('date')
        # Átalakítjuk Python datetime objektummá
        tx_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.now()
        
        new_tx = Transaction(
            total_amount=amount,
            date=tx_date,
            location_id=loc_id, # Most már biztosan szám vagy None
            user_id=1,
            wallet_id=int(request.form.get('wallet_id'))
        )
        db.session.add(new_tx)
        db.session.flush()

        new_item = TransactionItem(
            transaction_id=new_tx.id,
            amount=amount,
            category_id=request.form.get('category_id') or 1
        )
        db.session.add(new_item)
        db.session.commit()
        
        flash('Tranzakció rögzítve!')
        return redirect(url_for('index'))

    # GET kérés: adatok előkészítése
    today = datetime.now().strftime('%Y-%m-%d')
    locations = Location.query.all()
    wallets = Wallet.query.all()
    categories = Category.query.all()
    
    # Itt szimuláljuk a bejelentkezett felhasználó alapértelmezett zsebét
    # Később ez a current_user.default_wallet_id lesz
    default_wallet_id = 1 
    
    return render_template('add_transaction.html',
                           today=today,
                           locations=locations, 
                           wallets=wallets,
                           categories=categories,
                           default_wallet_id=default_wallet_id)

@app.route('/split/<int:tx_id>', methods=['GET', 'POST'])
def split_transaction(tx_id):
    # Lekérjük a tranzakciót az ID alapján, vagy 404 hiba, ha nem létezik
    tx = Transaction.query.get_or_404(tx_id)
    categories = Category.query.all()
    
    if request.method == 'POST':
        try:
            split_amount = float(request.form.get('split_amount'))
            new_category_id = int(request.form.get('category_id'))
            
            # Megkeressük az első (fő) tételt, amit bontani akarunk
            # Egy egyszerűbb logikával most feltételezzük, hogy az elsőt bontjuk
            main_item = tx.items[0]
            
            if split_amount < main_item.amount:
                # 1. Csökkentjük az eredeti tétel összegét
                main_item.amount -= split_amount
                
                # 2. Létrehozunk egy új tételt a leválasztott összeggel
                new_item = TransactionItem(
                    transaction_id=tx.id,
                    amount=split_amount,
                    category_id=new_category_id
                )
                db.session.add(new_item)
                db.session.commit()
                flash(f'Sikeresen leválasztottál {split_amount} Ft-ot!')
            else:
                flash('Hiba: A bontás összege nem lehet nagyobb vagy egyenlő az eredeti összeggel!', 'danger')
        except ValueError:
            flash('Érvénytelen összeget adtál meg!', 'danger')
            
        return redirect(url_for('index'))

    return render_template('split.html', tx=tx, categories=categories)

@app.route('/stats')
def stats():
    # 1. Lekérdezzük az összes kategóriát
    categories = Category.query.all()
    
    # 2. Lekérdezzük az utolsó 6 hónap adatait kategóriánként csoportosítva
    # (Ebben a példában az egyszerűség kedvéért az összes adatot nézzük hónapokra bontva)
    stats_data = db.session.query(
        extract('month', Transaction.date).label('month'),
        Category.name,
        func.sum(TransactionItem.amount).label('total')
    ).join(TransactionItem, Transaction.id == TransactionItem.transaction_id)\
     .join(Category, TransactionItem.category_id == Category.id)\
     .group_by('month', Category.name)\
     .order_by('month').all()

    # 3. Adatok formázása Chart.js számára
    # Elkészítünk egy listát a hónapokról (pl. 1, 2, 3...)
    months = sorted(list(set([int(d[0]) for d in stats_data])))
    
    # Kategóriánkénti adatsorok (datasets) felépítése
    datasets = []
    for cat in categories:
        cat_values = []
        for m in months:
            # Megkeressük az adott hónaphoz és kategóriához tartozó összeget
            amount = next((d[2] for d in stats_data if d[0] == m and d[1] == cat.name), 0)
            cat_values.append(amount)
        
        datasets.append({
            'label': cat.name,
            'data': cat_values,
            'backgroundColor': f'rgba({(cat.id*50)%255}, {(cat.id*80)%255}, 150, 0.7)' # Véletlenszerű színek
        })

    return render_template('stats.html', months=months, datasets=datasets)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
