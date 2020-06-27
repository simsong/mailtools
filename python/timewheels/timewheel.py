#!/usr/bin/env python3
"""
Demo program to draw some time wheels with matplotlib

Data flow:

                  [Extract Time information]
[data source] --->        ---------->           [time-aware representation]
                                                [time-wheel specification] 

                                                          |   [time wheel generator (this program)]
                                                         \|/ 
                                                  [time wheel output]

time is defined as Python datetime methods.

"""
import math
import matplotlib.pyplot as plt
import datetime

# Constants
RADIUS='radius'
DIVISION='division'
RING_COUNT='ring_count'
DIVISION_COUNT='division_count'



# Demo code to get things started
TIMEWHEEL_SPEC1 = {RADIUS:  lambda d:d.weekday(),
                   RING_COUNT: 7,
                   DIVISION: lambda d:d.hour,
                   DIVISION_COUNT: 24}


# https://matplotlib.org/gallery/color/named_colors.html
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as patches

"""
We want the following:

* Function that takes:
   input: # of rings, # of ring divisions
          ring #, division #
          color
   returns a pathes.Arc that fits in the correct place.

    example:
           # of rings = 7, # of divisions = 24
           ring # = 3 (wednesday), division # = 6 (6am)
* Function that takes a time-based data set that has:
      (datetime, event count)
      (description of the time wheel to create)
  turns it into:
      (ring #, division #, color)

* Function that takes:
  input:
    * input file of datetimes & counts
    * description of the time wheel to create
  output:
    * time wheel graph.
"""
   
COLORS=mcolors.TABLEAU_COLORS

if __name__=="__main__":
    fig, ax = plt.subplots() # note we must use plt.subplots, not plt.subplot

    radius = 0.25
    radius_max = math.sqrt(2)/2
    radius_delta = (radius_max-radius)/len(COLORS)
    
    for (ct,color) in enumerate(COLORS):
        r = radius_max - (radius_delta*ct)*2
        print(r)
        arc = patches.Arc((0.5, 0.5), r, r, theta1=45, theta2=60, color=color, linewidth=15)
        ax.add_artist(arc)

    fig.savefig('demo.png')
