from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'

    name = Column(String(250), nullable=False)
    email = Column(String(250))
    picture = Column(String(250))
    id = Column(Integer, primary_key=True)


class Supplier(Base):
    __tablename__ = 'supplier'

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)

    @property
    def serialize(self):
        # Return object data in easily serializeable format
        return {
            'name': self.name,
            'id': self.id,
            'creator': self.user.name,
          }


class Meal(Base):
    __tablename__ = 'meal'

    name = Column(String(80), nullable=False)
    id = Column(Integer, primary_key=True)
    description = Column(String(250))
    price = Column(String(8))
    supplier_id = Column(Integer, ForeignKey('supplier.id'))
    supplier = relationship(Supplier)
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)

    @property
    def serialize(self):
        # Return object data in easily serializeable format
        return {
            'name': self.name,
            'description': self.description,
            'id': self.id,
            'price': self.price,
            'supplier': self.supplier.name,
        }

#Added
engine = create_engine("postgresql://catalog:udac1ty!@127.0.0.1/catalog")

Base.metadata.create_all(engine)

