
dest_dir=/Volumes/ice2/ben/MAR/ATL11_with_corrections/rel002
#xover_file=$dest_dir/test_xovers.h5


xover_file=$dest_dir/rel002_crossover_data.h5
AT_file=$dest_dir/rel002_dump_every_2nd.h5

echo "Crossover_file: "$xover_file
echo "Along-track file: "$AT_file

[ -f $xover_file ] && [ -f $AT_file ] && echo "yep"
#exit

echo "SMB" 
append_SMB_ATL11.py --directory=/Volumes/ice1/tyler/ --model=MAR,RACMO,MERRA2-hybrid --region=GL $AT_file
append_SMB_ATL11.py --directory=/Volumes/ice1/tyler/ --model=MAR,RACMO,MERRA2-hybrid --region=GL $xover_file

#echo "SMB averages"
#append_SMB_averages_ATL11.py --directory=/Volumes/ice1/tyler/ --model=MAR --region=GL --year=2000,2019 $AT_file
#append_SMB_averages_ATL11.py --directory=/Volumes/ice1/tyler/ --model=MAR --region=GL --year=2000,2019 $xover_file

echo "SMB mean" 
append_SMB_mean_ATL11.py --directory=/Volumes/ice1/tyler/ --model=MAR --region=GL --year=1980,1995 $AT_file
append_SMB_mean_ATL11.py --directory=/Volumes/ice1/tyler/ --model=MAR --region=GL --year=1980,1995 $xover_file

#append_SMB_mean_ATL11.py --directory=/Volumes/ice1/tyler/ --model=MAR --region=GL --year=2000,2019 $AT_file
#append_SMB_mean_ATL11.py --directory=/Volumes/ice1/tyler/ --model=MAR --region=GL --year=2000,2019 $xover_file
