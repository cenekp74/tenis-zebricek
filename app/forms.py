from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, BooleanField
from wtforms.validators import DataRequired

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Heslo', validators=[DataRequired()])
    remember = BooleanField('Pamatuj si mě')
    submit = SubmitField('Přihlásit')
