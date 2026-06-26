from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, BooleanField
from wtforms.validators import DataRequired

class EditProfileForm(FlaskForm):
    picture = FileField('Profilová fotografie', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Povolené formáty: jpg, jpeg, png, webp.')
    ])
    submit = SubmitField('Uložit')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Heslo', validators=[DataRequired()])
    remember = BooleanField('Pamatuj si mě')
    submit = SubmitField('Přihlásit')
