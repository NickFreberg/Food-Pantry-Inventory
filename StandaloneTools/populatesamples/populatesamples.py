#!/usr/bin/python
import MySQLdb
import json

db = MySQLdb.connect(host="localhost",    # your host, usually localhost
                     user="root",         # your username
                     passwd="Capstone!2020",  # your password
                     db="sample_data")        # name of the data base

# you must create a Cursor object. It will let
#  you execute all the queries you need
cur = db.cursor()


# Use all the SQL you like
cur.execute("CREATE TABLE IF NOT EXISTS fpiweb_loctier (id INT AUTO_INCREMENT PRIMARY KEY, loc_tier VARCHAR(2), loc_tier_descr VARCHAR(20))")
cur.execute("CREATE TABLE IF NOT EXISTS fpiweb_palletbox (id INT AUTO_INCREMENT PRIMARY KEY, exp_year INT, exp_month_start INT, exp_month_end INT, box_status VARCHAR(15), box_id INT, pallet_id INT, product_id INT, box_number VARCHAR(8))")
cur.execute("CREATE TABLE IF NOT EXISTS fpiweb_pallet (id INT AUTO_INCREMENT PRIMARY KEY, pallet_status VARCHAR(15), location_id INT, name VARCHAR(200))")
cur.execute("CREATE TABLE IF NOT EXISTS fpiweb_product (id INT AUTO_INCREMENT PRIMARY KEY, prod_name VARCHAR(30), prod_cat_id INT)")
cur.execute("CREATE TABLE IF NOT EXISTS fpiweb_productcategory (id INT AUTO_INCREMENT PRIMARY KEY, prod_cat_name VARCHAR(30), prod_cat_descr longtext)")

# Get JSON data
file = open('/home/capstonetest/PycharmProjects/Food-Pantry-Inventory/StandaloneTools/populatesamples/templates/LocTier.json')
loctier = json.load(file)
file = open('/home/capstonetest/PycharmProjects/Food-Pantry-Inventory/StandaloneTools/populatesamples/templates/PalletBox.json')
palletbox = json.load(file)
file = open('/home/capstonetest/PycharmProjects/Food-Pantry-Inventory/StandaloneTools/populatesamples/templates//Pallet.json')
pallet = json.load(file)
file = open('/home/capstonetest/PycharmProjects/Food-Pantry-Inventory/StandaloneTools/populatesamples/templates//Product.json')
product = json.load(file)
file = open('/home/capstonetest/PycharmProjects/Food-Pantry-Inventory/StandaloneTools/populatesamples/templates//ProductCategory.json')
productcategory = json.load(file)

for tier in loctier:
    print(tier['fields']['loc_tier'], (tier['fields']['loc_tier_descr']))
    loc_tier = tier['fields']['loc_tier']
    loc_tier_descr = tier['fields']['loc_tier_descr']
    sql = "INSERT INTO fpiweb_loctier(loc_tier, loc_tier_descr) VALUES(%s, %s)"
    val = (str(loc_tier), str(loc_tier_descr))
    cur.execute(sql, val)



db.close()