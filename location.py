from geopy.geocoders import Nominatim
from googletrans import Translator
import pandas as pd
from datetime import datetime

def isfloat(i):
    try:
        float(i)
        return True
    except:
        return False

translator = Translator()

geolocator = Nominatim(user_agent="def",timeout=100)

col_list = ["Date Created","Latitude","Longitude","Path"]

dt = []

df = pd.read_csv("Enter csv path", usecols = col_list)#Enter the csv path

for i,j,k,l in zip(df["Date Created"],df["Latitude"],df["Longitude"],df["Path"]):
    if isfloat(j) == True:
        lat = j+","+k
        location = geolocator.reverse(lat)
        address = translator.translate(location.address)
        address = address.text

        i = i[:(len(i)-4)]
        dt1=[]

        dt1.append(i)
        dt1.append(address)
        dt1.append(l)
        dt.append(dt1)

dt.sort(key = lambda x:x[0])
for i in dt:
    for j in i:
        print(j)
    print('\n')
    #print(type(i))
