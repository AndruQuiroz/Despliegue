from flask import Flask, render_template, request, redirect, flash, jsonify
from pymongo import MongoClient
import os
from werkzeug.utils import secure_filename
from flask_cors import CORS
import openai
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests

app = Flask(__name__)
app.secret_key = "secreto_seguro"
app.config['UPLOAD_FOLDER'] = 'static/images'  # Ruta donde se guardarán las imágenes
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}  # Tipos de archivos permitidos
CORS(app)

# 🔑 Tu clave API de OpenAI (reemplaza por la tuya si la cambiaste)
openai.api_key = "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"

# 🔌 Conexión a MongoDB
try:
    client = MongoClient("mongodb://localhost:27017/")
    db = client["shoppingDB"]
    print("✅ Conectado a MongoDB correctamente.")
except Exception as e:
    print("❌ Error al conectar a MongoDB:", e)

# 🔐 Configuración de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # Página de login a la que redirigir si no está logueado

class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = str(id)  # Flask-Login requiere que el ID sea un string
        self.username = username
        self.password_hash = password_hash

# Cargar el usuario
@login_manager.user_loader
def load_user(user_id):
    user_data = db.users.find_one({"_id": user_id})
    if user_data:
        return User(id=user_data["_id"], username=user_data["username"], password_hash=user_data["password_hash"])
    return None

# Función para verificar si el archivo tiene una extensión permitida
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# 🧠 Función para generar el análisis de comportamiento
def generar_resumen_usuario(purchases, bids):
    prompt = (
        "Analiza el comportamiento del usuario basado en estas compras y pujas.\n\n"
        "Extrae conclusiones como:\n"
        "- Cuánto gastó en total\n"
        "- Cuál fue su compra más cara\n"
        "- Cuántas compras ha hecho\n"
        "- El promedio de gasto\n"
        "- Si compra más barato o caro últimamente\n"
        "- Cuántas pujas hizo\n"
        "- Cuántas ganó o perdió\n"
        "- Oferta más alta realizada\n"
        "- Qué tipo de comportamiento refleja (arriesgado, conservador, etc)\n\n"
        f"Compras: {purchases}\n"
        f"Pujas: {bids}\n\n"
        "Da un resumen claro y directo, como si lo explicara un asesor experto."
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[ 
            {"role": "system", "content": "Eres un analista de datos experto que genera resúmenes útiles y profesionales para usuarios finales."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=300,
        temperature=0.7
    )

    return response.choices[0].message["content"].strip()

# 🎯 Recomendaciones generadas por IA basadas en el resumen
def obtener_recomendaciones(analisis):
    prompt = (
        "A partir del siguiente análisis del comportamiento del usuario, "
        "genera tres recomendaciones personalizadas para mejorar sus decisiones en compras y subastas:\n\n"
        f"{analisis}\n\n"
        "Recomendaciones:"
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[ 
            {"role": "system", "content": "Eres un asesor experto en hábitos de consumo y subastas."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=350,
        temperature=0.7
    )

    recomendaciones_crudas = response.choices[0].message["content"].strip()
    recomendaciones = [line.strip("•- ").strip() for line in recomendaciones_crudas.split("\n") if line.strip()]

    # 🧾 Guardar en la base de datos
    db.recomendaciones.insert_one({
        "resumen": analisis,
        "recomendaciones": recomendaciones,
        "fecha": datetime.now()
    })

    return recomendaciones

# 🌐 Rutas principales

# Ruta principal
@app.route('/')
def index():
    return render_template("base.html")  # Muestra la página base con el menú lateral y el área principal

# Ruta de registro
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Obtener los datos del formulario
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validar contraseñas
        if password != confirm_password:
            flash("⚠ Las contraseñas no coinciden.", "error")
            return redirect('/register')
        
        # Encriptar la contraseña
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Verificar si el usuario ya existe
        existing_user = db.user.find_one({"email": email})
        if existing_user:
            flash("⚠ Este correo ya está registrado.", "error")
            return redirect('/register')

        # Insertar nuevo usuario en la base de datos
        db.user.insert_one({"email": email, "password": hashed_password})
        flash("✅ Usuario registrado con éxito.", "success")
        return redirect('/login')  # Redirigir al login

    return render_template('register.html')  # Mostrar formulario de registro

# 🌐 Ruta para el login de usuarios
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Buscar el usuario en la base de datos
        user = db.user.find_one({"email": email})
        if user and check_password_hash(user['password'], password):
            flash("✅ Inicio de sesión exitoso.", "success")
            return redirect('/')  # Redirige a la página principal
        else:
            flash("⚠ Correo o contraseña incorrectos.", "error")
            return redirect('/login')  # Redirige al login si las credenciales son incorrectas

    return render_template('login.html')  # Carga el formulario de inicio de sesión

# Ruta de logout
@app.route('/logout')
@login_required
def logout():
    logout_user()  # Cierra la sesión del usuario
    flash("Has cerrado sesión exitosamente.", "success")
    return redirect('/login')

# Ruta de perfil, protegida por login
@app.route('/profile')
@login_required
def profile():
    return render_template("profile.html")  # Esta página ahora está protegida y requiere autenticación

@app.route('/products')
def products():
    # Obtener todos los productos desde MongoDB
    products = list(db.products.find())
    return render_template("products.html", products=products)


# Función para generar imagen con IA
def generate_image_with_ai(name, description):
    try:
        # Generar la imagen con DALL-E (usando OpenAI)
        prompt = f"Genera una imagen de un producto con el nombre {name} y la descripción {description}."
        response = openai.Image.create(
            prompt=prompt,  # Usamos el nombre y descripción como el "prompt"
            n=1,  # Una sola imagen
            size="1024x1024"  # Tamaño de la imagen
        )

        # Verificar si la respuesta de la API fue exitosa
        if 'data' not in response or len(response['data']) == 0:
            raise Exception("No se recibió una respuesta válida de la API de OpenAI.")

        # Obtener la URL de la imagen generada
        image_url = response['data'][0]['url']

        # Descargar la imagen generada
        image_response = requests.get(image_url)
        
        if image_response.status_code == 200:
            # Guardar la imagen descargada en static/images
            filename = secure_filename(f"{name.replace(' ', '_')}.jpg")
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            with open(image_path, 'wb') as file:
                file.write(image_response.content)

            # Guardar la ruta relativa en MongoDB
            image_rel_path = f"images/{filename}"
            return image_rel_path
        else:
            raise Exception(f"Error al descargar la imagen desde OpenAI. Código de estado: {image_response.status_code}")
    except Exception as e:
        # Capturar cualquier excepción y devolver el error detallado
        raise Exception(f"Error al generar la imagen: {str(e)}")
    

# Ruta para generar la imagen con IA y devolverla al frontend
@app.route('/generate_image', methods=['POST'])
def generate_image():
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description')

        # Generar imagen con IA
        image_rel_path = generate_image_with_ai(name, description)

        # Devolver la ruta de la imagen generada
        return jsonify({"imagePath": image_rel_path})
    except Exception as e:
        # En caso de error, devolver el mensaje de error con más detalles
        return jsonify({"error": f"Error al generar la imagen: {str(e)}"}), 500

# Ruta para publicar productos
@app.route('/publish', methods=['GET', 'POST'])
def publish():
    if request.method == 'POST':
        # Obtener los datos del formulario
        name = request.form['name']
        description = request.form['description']
        price = request.form['price']
        
        image_rel_path = None  # Inicializamos la variable de ruta de imagen
        
        # Verificar si se ha cargado un archivo
        if 'image' not in request.files or not request.files['image'].filename:
            flash("⚠ No se ha seleccionado ninguna imagen. Generando imagen con IA...", "info")
            prompt = f"Imagen para producto: {name}. Descripción: {description}"
            try:
                # Llamar la función para generar imagen con IA
                image_rel_path = generate_image_with_ai(prompt)
                flash("✅ Imagen generada con éxito.", "success")
            except Exception as e:
                flash(f"⚠ Error al generar la imagen con IA: {str(e)}", "error")
                return redirect('/publish')
        else:
            file = request.files['image']
            if file and allowed_file(file.filename):
                # Guardar la imagen en el directorio estático
                filename = secure_filename(file.filename)
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(image_path)
                
                # Guardar la ruta de la imagen en MongoDB
                image_rel_path = f"images/{filename}"
            else:
                flash("⚠ La imagen debe ser de tipo png, jpg o jpeg.", "error")
                return redirect('/publish')

        # Insertar el producto en la base de datos
        db.products.insert_one({
            "name": name,
            "description": description,
            "price": price,
            "image": image_rel_path  # Guardar la ruta relativa de la imagen
        })

        flash("✅ Producto publicado con éxito.", "success")
        return redirect('/products')  # Redirigir a la página de productos después de publicar

    return render_template("publish.html")  # Mostrar formulario de publicación




@app.route('/auctions', methods=['GET'])
def auctions():
    # Obtener todas las subastas activas
    auctions = list(db.auction.find({"status": "active"}))
    return render_template("auctions.html", auctions=auctions)


@app.route('/create_auction', methods=['GET', 'POST'])
#@login_required  # Solo los usuarios logueados pueden crear una subasta
def create_auction():
    if request.method == 'POST':
        # Obtener los datos del formulario
        name = request.form['name']
        description = request.form['description']
        initial_price = request.form['initial_price']
        start_date = request.form['start_date']
        end_date = request.form['end_date']

        # Obtener las imágenes
        images = []
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                images.append(f"images/{filename}")

        # Insertar la subasta en la base de datos
        auction = {
            "name": name,
            "description": description,
            "initial_price": float(initial_price),
            "start_date": start_date,
            "end_date": end_date,
            "images": images,
            "user_id": current_user.id,
            "status": "active"
        }

        db.auction.insert_one(auction)
        flash("Subasta creada con éxito.", "success")
        return redirect('/auctions')

    return render_template('create_auction.html')


@app.route('/admin')
def admin():
    bids = list(db.bids.find({}, {"_id": 0}))
    pending_bids = list(db.bids.find({"status": "Pendiente"}, {"_id": 0}))
    return render_template("admin.html", bids=bids, pending_bids=pending_bids)


@app.route('/update_status', methods=['POST'])
def update_status():
    auction_id = request.form.get('auctionId').strip()
    new_status = request.form.get('status').strip()

    if not auction_id or not new_status:
        flash("⚠ Error: Datos inválidos enviados.", "error")
        return redirect('/admin')

    result = db.bids.update_many({"auctionId": auction_id}, {"$set": {"status": new_status}})

    if result.modified_count > 0:
        flash(f"✅ {result.modified_count} oferta(s) actualizada(s) a '{new_status}'", "success")
    else:
        flash(f"⚠ No se realizó ninguna actualización para {auction_id}.", "error")

    return redirect('/admin')

@app.route('/historial_recomendaciones')
def historial_recomendaciones():
    historial = list(db.recomendaciones.find({}, {"_id": 0}).sort("fecha", -1))
    return render_template("historial.html", historial=historial)

@app.route('/historial_compras', methods=['GET', 'POST'])
def historial_compras():
    purchases = list(db.purchases.find({}, {"_id": 0}))
    bids = list(db.bids.find({}, {"_id": 0}))
    resumen = None
    recomendaciones = None

    if request.method == 'POST':
        accion = request.form.get('accion')

        if accion == 'analisis':
            resumen = generar_resumen_usuario(purchases, bids)

        elif accion == 'recomendaciones':
            resumen = request.form.get('resumen')
            recomendaciones = obtener_recomendaciones(resumen)

    return render_template("historial_compras.html", purchases=purchases, bids=bids, resumen=resumen, recomendaciones=recomendaciones)

if __name__ == '__main__':
    app.run(debug=True)
