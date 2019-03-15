### purpose
# sbatch crisp cmd if all bamfiles have been created
###

### usage
# python start_crisp.py parentdir pool
### 

### fix
# uncomment sbatch!
# assumes equal sample size across pools 
### 

### imports
import sys, os, pickle, time, random
from os import path as op
###

def pklload(path):
    pkl = pickle.load(open(path,'rb'))
    return pkl

def fs(DIR):
    return sorted([op.join(DIR,f) for f in os.listdir(DIR)])

def getfiles():
    global pooldir
    pooldir = op.join(parentdir,pool)
    samps   = pklload(op.join(parentdir,'poolsamps.pkl'))[pool]
    found   = fs(op.join(pooldir,'realign'))
    files   = dict((samp,f.replace(".bai",".bam")) for f in found for samp in samps if samp in f and f.endswith('.bai'))
    return (samps,files)

def checkfiles():
    # get the list of file names
    samps,files = getfiles()
    if not len(samps) == len(files):
        unmade = [samp for samp in samps if not samp in files]
        text = ''
        for missing in unmade:
            text = text + "\t%s\n" % missing
        os.system('echo "still missing files from these samps:\n%s\n%s is exiting\n"' % (text,thisfile))
        exit()
    return list(files.values())

def makedir(DIR):
    if not op.exists(DIR):
        os.makedirs(DIR)
    return DIR
        
def create_reservation(exitneeded = False):
    global crispdir
    crispdir = makedir(op.join(pooldir,'shfiles/crisp'))
    file = op.join(crispdir,'%s_crisp_reservation.sh' % pool)
    jobid = os.environ['SLURM_JOB_ID']
    if not op.exists(file):
        with open(file,'w') as o:
            o.write("%s" % jobid)
    else:
        exitneeded = True
    time.sleep(random.random()*15)
    with open(file,'r') as o:
        fjobid = o.read().split()[0]
    if not fjobid == jobid or exitneeded == True:
        # just in case two jobs try at nearly the same time
        os.system('echo another job has already created start_crisp.sh for %s' % pool)
        exit()
        
def getcmd(files,bam_file_list,bedfile):
    locals().update({'pool':pool})
    bams = ' --bam '.join(files)
    num  = bedfile.split("_")[-1].split(".bed")[0]
    ref  = pklload(op.join(parentdir,'poolref.pkl'))[pool]
    outdir   = makedir(op.join(pooldir,'crisp'))
    outfile  = op.join(outdir,'%(pool)s_crisp_bedfile_%(num)s.vcf' % locals())
    poolsize = pklload(op.join(parentdir,'ploidy.pkl'))[pool]
    logfile  = outfile.replace(".vcf",".log") 
    return ('''$CRISP_DIR/CRISP --bam %(bams)s --ref %(ref)s --VCF %(outfile)s \
--poolsize %(poolsize)s --mbq 20 --minc 5 --bed %(bedfile)s > %(logfile)s
''' % locals(),
            num,outfile,logfile)

def make_sh(files,bedfile):
    locals().update({'pool':pool,'pooldir':pooldir})
    bam_file_list = '$SLURM_TMPDIR/bam_file_list.txt' # replace with function if pools unequal
    cmd, num, outfile, logfile = getcmd(files,bam_file_list,bedfile)
    tablefile = outfile.replace(".vcf","_table.txt")
    text = '''#!/bin/bash
#SBATCH --ntasks=1
#SBATCH --job-name=%(pool)s-crisp_bedfile_%(num)s
#SBATCH --time=11:59:00
#SBATCH --mem=4000M
#SBATCH --output=%(pool)s-crisp_bedfile_%(num)s_%%j.out

source $HOME/.bashrc
export PYTHONPATH="${PYTHONPATH}:$HOME/pipeline"

# run CRISP (commit 60966e7)
%(cmd)s

# if any other crisp jobs are hanging due to priority, change the account
python $HOME/pipeline/balance_queue.py crisp

# vcf -> table (multiallelic to multiple lines, filtered in combine_crisp.py
module load gatk/4.1.0.0
gatk VariantsToTable --variant %(outfile)s -F CHROM -F POS -F REF -F ALT -F AF -F QUAL \
-F DP -F CT -F AC -F VT -F EMstats -F HWEstats -F VF -F VP -F HP -F MQS -F TYPE -F FILTER \
-O %(tablefile)s --split-multi-allelic
module unload gatk

# combine crisp files
python $HOME/pipeline/combine_crisp.py %(pooldir)s

# gzip outfiles to save space
cd $(dirname %(outfile)s)
gzip %(outfile)s
rm %(logfile)s

''' % locals()
    file = op.join(crispdir,'%(pool)s-crisp_bedfile_%(num)s.sh' % locals())
    with open(file,'w') as o:
        o.write("%s" % text)
    return file

def sbatch(file):
    os.chdir(op.dirname(file))
    os.system('sbatch %s' % file)
    os.system('echo "sbatched %s"' % file)
    
def get_bedfiles():
    ref = pklload(op.join(parentdir,'poolref.pkl'))[pool]
    beddir = op.join(op.dirname(ref),'bedfiles_%s' % op.basename(ref).replace(".fasta",""))
    return [f for f in fs(beddir) if f.endswith('.bed')]
        
def create_sh(files):
    bedfiles = get_bedfiles()
    for bedfile in bedfiles:
        file = make_sh(files,bedfile)
        sbatch(file)
    os.system('echo "done sbatching, exiting %s"' % thisfile)

def main():
    """Start CRISP if it's appropriate to do so"""
   
    # check to see if all bam files have been created; if not: exit()
    files = checkfiles()
    
    # create reservation so other files don't try and write files.sh, exit() if needed
    create_reservation()
    
    # create .sh file and submit to scheduler
    create_sh(files)
    
    # balance queue
    os.system('python $HOME/pipeline/balance_queue.py crisp')
    
    # cancel reservation
        # I don't think I need to do this unless I find that jobs are dying unexpectedly
    
if __name__ == "__main__":
    ### args
    global thisfile, parentdir, pool
    thisfile, parentdir, pool = sys.argv
    
    main()
        