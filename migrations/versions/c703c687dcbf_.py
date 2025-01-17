"""empty message

Revision ID: c703c687dcbf
Revises: 61a3c54cbe7f
Create Date: 2021-04-10 09:40:35.380724

"""
import pandas as pd
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c703c687dcbf'
down_revision = '61a3c54cbe7f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('vakciny',
    sa.Column('vyrobce', sa.Unicode(), nullable=False),
    sa.Column('vakcina', sa.Unicode(), nullable=False),
    sa.Column('davky', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('vyrobce'),
    sa.UniqueConstraint('vakcina')
    )
    op.create_table('dodavky_vakcin',
    sa.Column('datum', sa.Date(), nullable=False),
    sa.Column('vyrobce', sa.Unicode(), nullable=False),
    sa.Column('pocet', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['vyrobce'], ['vakciny.vyrobce'], ),
    sa.PrimaryKeyConstraint('datum', 'vyrobce')
    )

    connection = op.get_bind()
    connection.execute("INSERT INTO vakciny (vyrobce, vakcina, davky) VALUES('Pfizer', 'Comirnaty', 2)")
    connection.execute("INSERT INTO vakciny (vyrobce, vakcina, davky) VALUES('Moderna', 'COVID-19 Vaccine Moderna', 2)")
    connection.execute("INSERT INTO vakciny (vyrobce, vakcina, davky) VALUES('AstraZeneca', 'VAXZEVRIA', 2)")
    connection.execute("INSERT INTO vakciny (vyrobce, vakcina, davky) VALUES('Janssen', 'COVID-19 Vaccine Janssen', 1)")
    connection.execute("INSERT INTO vakciny (vyrobce, vakcina, davky) VALUES('Novavax', 'Novavax', 2)")
    connection.execute("INSERT INTO vakciny (vyrobce, vakcina, davky) VALUES('CureVac', 'CureVac', 2)")
    connection.execute("INSERT INTO vakciny (vyrobce, vakcina, davky) VALUES('GSK', 'GSK', 2)")

    op.create_foreign_key(None, 'ockovani_distribuce', 'vakciny', ['vyrobce'], ['vyrobce'])
    op.create_foreign_key(None, 'ockovani_lide', 'vakciny', ['vakcina'], ['vakcina'])
    op.create_foreign_key(None, 'ockovani_spotreba', 'vakciny', ['vyrobce'], ['vyrobce'])

    df = pd.read_csv('./data/dodavky_vakcin/2021-04-10.csv')
    df['datum'] = pd.to_datetime(df['Měsíc'], format='%d. %m. %Y')
    df = df.rename({'AZ': 'AstraZeneca'}, axis=1)
    df = df.melt(id_vars=['datum'], value_vars=['Pfizer', 'Moderna', 'AstraZeneca', 'CureVac', 'Janssen', 'Novavax', 'GSK'],
                 var_name='vyrobce', value_name='pocet')
    df.to_sql('dodavky_vakcin', connection, if_exists='replace', index=False)


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'ockovani_spotreba', type_='foreignkey')
    op.drop_constraint(None, 'ockovani_lide', type_='foreignkey')
    op.drop_constraint(None, 'ockovani_distribuce', type_='foreignkey')
    op.drop_table('dodavky_vakcin')
    op.drop_table('vakciny')
    # ### end Alembic commands ###
