#!/bin/sh
echo "Generating initial kml files..."
./mongo_kml.py
echo "Starting sysinfodb.py..."
./sysinfodb.py
