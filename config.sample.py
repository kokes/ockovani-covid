import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    SQLALCHEMY_DATABASE_URI = 'postgresql://ockovani:ockovani@ockovani:5432/ockovani'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
