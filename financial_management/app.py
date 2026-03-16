import os

import locale

from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, User, Wallet, Currency, Location, Transaction, TransactionItem, Category, Project, Tag
from datetime import datetime
from sqlalchemy import func, extract

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fejlesztoi-kulcs-123' # Később változtasd meg!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db.init_app(app)

# Beállítjuk a magyar nyelvi környezetet (ha a rendszer támogatja)
try:
    locale.setlocale(locale.LC_ALL, 'hu_HU.UTF-8')
except:
    locale.setlocale(locale.LC_ALL, '') # Alapértelmezett, ha a magyar nem elérhető

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
    categories_raw = Category.query.all()
    categories = sorted(categories_raw, key=lambda x: locale.strxfrm(x.name))
    
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
    categories_raw = Category.query.all()
    categories = sorted(categories_raw, key=lambda x: locale.strxfrm(x.name))
    
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
    total_monthly_limit = db.session.query(func.sum(Category.monthly_limit)).scalar() or 0

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

        # Hónap nevek magyarul
        honapok_nevei = ["Január", "Február", "Március", "Április", "Május", "Június", 
                        "Július", "Augusztus", "Szeptember", "Október", "November", "December"]
        
        # A hónap számokat (1-12) kicseréljük nevekre a JavaScript számára
        month_labels = [honapok_nevei[m-1] for m in months]

    # 4. A havi keret átadása a frontendnek
    # Készítünk egy listát, ami minden hónaphoz ugyanazt a limit értéket rendeli
    limit_data = [total_monthly_limit for _ in months]

    # Csak tesztnek az app.py-ba, ha üres lenne:
    if not months:
        months = [3] # Március
        month_labels = ["Március"]
        limit_data = [100000]
        datasets = [{'label': 'Teszt', 'data': [50000]}]

    return render_template('stats.html', 
                            months=month_labels, 
                            datasets=datasets,
                            limit_value=total_monthly_limit,
                            limit_data=limit_data)

@app.route('/delete_transaction/<int:tx_id>')
def delete_transaction(tx_id):
    # Megkeressük a tranzakciót, ha nincs ilyen, 404-es hibát dob
    tx = Transaction.query.get_or_404(tx_id)
    
    try:
        db.session.delete(tx)
        db.session.commit()
        flash('Tranzakció sikeresen törölve!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hiba történt a törlés során: {str(e)}', 'danger')
        
    return redirect(url_for('index'))

@app.route('/categories', methods=['GET', 'POST'])
def manage_categories():
    if request.method == 'POST':
        # ... (a mentési logika változatlan marad)
        new_cat_name = request.form.get('new_category_name')
        new_cat_limit = request.form.get('new_category_limit')
        
        if new_cat_name:
            new_cat = Category(name=new_cat_name, monthly_limit=float(new_cat_limit or 0))
            db.session.add(new_cat)
        
        categories_raw = Category.query.all()
        categories = sorted(categories_raw, key=lambda x: locale.strxfrm(x.name))
        for cat in categories:
            name = request.form.get(f'name_{cat.id}')
            limit = request.form.get(f'limit_{cat.id}')
            if name:
                cat.name = name
                cat.monthly_limit = float(limit or 0)
        
        db.session.commit()
        flash('Kategóriák frissítve!', 'success')
        return redirect(url_for('manage_categories'))

    # GET kérésnél: Lekérés ABC sorrendben a 'name' oszlop alapján
    categories_raw = Category.query.all()
    categories = sorted(categories_raw, key=lambda x: locale.strxfrm(x.name))
    return render_template('categories.html', categories=categories)

@app.route('/settings/wallets', methods=['GET', 'POST'])
def manage_wallets():
    if request.method == 'POST':
        new_name = request.form.get('new_name')
        if new_name:
            # Egyelőre az első pénznemet rendeljük hozzá (HUF)
            huf = Currency.query.filter_by(code='HUF').first()
            db.session.add(Wallet(name=new_name, currency_id=huf.id))
        
        # Meglévők frissítése
        for wallet in Wallet.query.all():
            name = request.form.get(f'name_{wallet.id}')
            if name: wallet.name = name
        
        db.session.commit()
        return redirect(url_for('manage_wallets'))
    
    wallets = Wallet.query.all()
    return render_template('manage_items.html', items=wallets, title="Zsebek", type="wallets")

@app.route('/settings/locations', methods=['GET', 'POST'])
def manage_locations():
    if request.method == 'POST':
        # Új helyszín hozzáadása
        new_name = request.form.get('new_name')
        new_cat_id = request.form.get('new_category_id')
        
        if new_name:
            new_loc = Location(
                name=new_name, 
                default_category_id=int(new_cat_id) if new_cat_id else None
            )
            db.session.add(new_loc)
        
        # Meglévők frissítése
        for loc in Location.query.all():
            name = request.form.get(f'name_{loc.id}')
            cat_id = request.form.get(f'category_{loc.id}')
            if name:
                loc.name = name
                loc.default_category_id = int(cat_id) if cat_id else None
            
        db.session.commit()
        flash('Helyszínek frissítve!', 'success')
        return redirect(url_for('manage_locations'))
    
    # Adatok lekérése ABC rendben
    locations_raw = Location.query.all()
    locations = sorted(locations_raw, key=lambda x: locale.strxfrm(x.name))
    
    categories_raw = Category.query.all()
    categories = sorted(categories_raw, key=lambda x: locale.strxfrm(x.name))
    
    return render_template('manage_locations.html', 
                           locations=locations, 
                           categories=categories)

@app.route('/settings/projects', methods=['GET', 'POST'])
def manage_projects():
    if request.method == 'POST':
        new_name = request.form.get('new_name')
        new_budget = request.form.get('new_budget')
        if new_name:
            db.session.add(Project(name=new_name, budget=float(new_budget or 0)))
        
        for proj in Project.query.all():
            name = request.form.get(f'name_{proj.id}')
            budget = request.form.get(f'budget_{proj.id}')
            if name:
                proj.name = name
                proj.budget = float(budget or 0)
        db.session.commit()
        return redirect(url_for('manage_projects'))
    
    projects_raw = Project.query.all()
    projects = sorted(projects_raw, key=lambda x: locale.strxfrm(x.name))
    return render_template('manage_items.html', items=projects, title="Projektek", type="projects")
    
@app.route('/settings/tags', methods=['GET', 'POST'])
def manage_tags():
    if request.method == 'POST':
        new_name = request.form.get('new_name')
        if new_name:
            # Tisztítsuk meg a címkét (ne legyen benne szóköz az elején/végén)
            db.session.add(Tag(name=new_name.strip()))
        
        for tag in Tag.query.all():
            name = request.form.get(f'name_{tag.id}')
            if name: tag.name = name.strip()
            
        db.session.commit()
        return redirect(url_for('manage_tags'))
    
    tags_raw = Tag.query.all()
    tags = sorted(tags_raw, key=lambda x: locale.strxfrm(x.name))
    return render_template('manage_items.html', items=tags, title="Címkék", type="tags")

@app.route('/edit/<int:tx_id>', methods=['GET', 'POST'])
def edit_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    
    if request.method == 'POST':
        # 1. Alapadatok frissítése
        tx.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
        tx.location_id = int(request.form.get('location_id')) or None
        tx.wallet_id = int(request.form.get('wallet_id'))
        tx.total_amount = float(request.form.get('total_amount'))

        # 2. Meglévő tételek frissítése
        current_item_ids = [item.id for item in tx.items]
        for item_id in current_item_ids:
            item = TransactionItem.query.get(item_id)
            item.amount = float(request.form.get(f'item_amount_{item_id}'))
            item.category_id = int(request.form.get(f'item_category_{item_id}'))
            item.project_id = request.form.get(f'item_project_{item_id}')
            if item.project_id: item.project_id = int(item.project_id)
            
            # Címkék kezelése (Many-to-Many)
            tag_ids = request.form.getlist(f'item_tags_{item_id}')
            item.tags = [Tag.query.get(int(tid)) for tid in tag_ids]

        # 3. Új tétel hozzáadása (Bontás funkció) és az első tétel csökkentése
        new_amount_raw = request.form.get('new_item_amount')
        if new_amount_raw and float(new_amount_raw) > 0:
            new_amount = float(new_amount_raw)
            
            # Megkeressük az első tételt (ezt tekintjük "fő" tételnek, amiből levonunk)
            main_item = tx.items[0]
            
            if new_amount < main_item.amount:
                # Levonjuk a fő tételből
                main_item.amount -= new_amount
                
                # Létrehozzuk az új tételt
                new_item = TransactionItem(
                    transaction_id=tx.id,
                    amount=new_amount,
                    category_id=int(request.form.get('new_item_category'))
                )
                db.session.add(new_item)
            else:
                flash('Hiba: Az új tétel összege nem lehet nagyobb, mint a maradék!', 'danger')

        db.session.commit()
        flash('Tranzakció sikeresen frissítve!', 'success')
        return redirect(url_for('index'))

    # Adatok lekérése a listákhoz
    locations = sorted(Location.query.all(), key=lambda x: locale.strxfrm(x.name))
    categories = sorted(Category.query.all(), key=lambda x: locale.strxfrm(x.name))
    wallets = Wallet.query.all()
    projects = sorted(Project.query.all(), key=lambda x: locale.strxfrm(x.name))
    tags = sorted(Tag.query.all(), key=lambda x: locale.strxfrm(x.name))
    
    return render_template('edit_transaction.html', tx=tx, locations=locations, 
                           categories=categories, wallets=wallets, 
                           projects=projects, tags=tags)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
