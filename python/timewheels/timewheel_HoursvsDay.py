'''
#restr_data = data.groupby(['Time','Day of Week']).mean()['Result']
#print(restr_data)

#weekday_vs_hour = data.pivot_table(columns=pd.to_datetime(data['Day']).dt.day_name(),index=data['Time'],aggfunc='sum')
#print(weekday_vs_hour)
#month_vs_year = df.pivot_table(columns=df['Date_time'].dt.month,index=df['Date_time'].dt.year.apply(is_top_years),aggfunc='count',values='city')

#for i,row_name in enumerate(data.iterrows()):
#    for x,y,z in row_name.:
#        print("rowname:",y)
'''
import csv
import pandas as pd
import matplotlib as mpl
import matplotlib.cm as cm
import numpy as np
import matplotlib.pyplot as plt

data = pd.read_csv("August_report.csv")


data['Day'] = pd.to_datetime(data['Day']).dt.day_name()
#print(data)

cats = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
data['Day'] = pd.Categorical(data['Day'], categories=cats, ordered=True)

data = data.sort_values('Day')

table= pd.crosstab(data.Day,data.Time,values=data.Result,aggfunc=np.sum)
print(table.T)

n, m = table.shape

inner_r=0.25


color_map = cm.cool 
normlizer = mpl.colors.Normalize(vmin = 0, vmax = 10000) 



figure, axes = plt.subplots() 

vmin=0
vmax=10000
    
vmin= table.min().min() if vmin is None else vmin
vmax= table.max().max() if vmax is None else vmax
    
centre_circle = plt.Circle((0,0),inner_r,edgecolor='black',facecolor='white',fill=True,linewidth=0.25)
plt.gcf().gca().add_artist(centre_circle)
#norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
#print(norm)
cmapper = cm.ScalarMappable(norm=normlizer, cmap=color_map)
for i, (row_name, row) in enumerate(table.iterrows()):
    labels = None if i > 0 else table.columns
    wedges = plt.pie([1] * m,radius=inner_r+float(n-i)/n, colors=[cmapper.to_rgba(x) for x in row.values], 
        labels=labels, startangle=90, counterclock=False, wedgeprops={'linewidth':-1})
    plt.setp(wedges[0], edgecolor='white',linewidth=1.5)
    wedges = plt.pie([1], radius=inner_r+float(n-i-1)/n, colors=['w'], labels=[row_name], counterclock=False, startangle=270, wedgeprops={'linewidth':0})
    plt.setp(wedges[0], edgecolor='white',linewidth=1.5)
    	


#plt.figure(figsize=(8,8))
#plt.colorbar()
plt.show()

'''
figure.subplots_adjust(bottom = 0.5) 
  
figure.colorbar(mpl.cm.ScalarMappable(norm = normlizer, 
               cmap = color_map), 
               cax = axes, orientation ='horizontal', 
               label ='Arbitary Units') 

'''	
