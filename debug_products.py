#!/usr/bin/env python3
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firebase
cred_path = '/etc/secret/serviceAccountKey.json'
if not os.path.exists(cred_path):
    cred_path = 'serviceAccountKey.json'

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

print("Fetching all products from Firestore...\n")

products = list(db.collection('products').stream())
print(f"Total products in Firestore: {len(products)}\n")

for i, doc in enumerate(products, 1):
    data = doc.to_dict()
    print(f"{i}. ID: {doc.id}")
    print(f"   Name: {data.get('name')}")
    print(f"   Category: {data.get('category')}")
    print(f"   Price: {data.get('price')}")
    print(f"   InStock: {data.get('inStock')}")
    print(f"   IsActive: {data.get('isActive')}")
    print(f"   CreatedAt: {data.get('createdAt')}")
    print(f"   ImageUrl: {data.get('imageUrl', 'None')[:50]}...")
    print()
