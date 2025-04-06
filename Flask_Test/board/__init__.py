from flask import Flask
from flask_mail import Mail
from board import pages

mail = Mail()  

def create_app():
    app = Flask(__name__)
    
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'capstonetestingtester@gmail.com'  
    app.config['MAIL_PASSWORD'] = 'hinzuxesgkupprvn'  

    mail.init_app(app)  

    app.register_blueprint(pages.bp)
    return app

if __name__ == '__main__':
    app = create_app() 
    app.run(debug=True)