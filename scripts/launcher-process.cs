// AGPL-3.0. Windows supervision without services, scheduled tasks or extra packages.
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Collections.Generic;

public static class DshLauncherProcess {
    public static void ReplaceFile(string source,string destination) {
        File.Replace(source,destination,null);
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr attrs, string name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int type, IntPtr info, uint size);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("iphlpapi.dll")] static extern uint GetExtendedTcpTable(IntPtr table, ref int size, bool sort, int family, int type, uint reserved);
    // Keep the handle alive until worker process exit. Kernel closes it on
    // abnormal exit too, ending only that worker's children.
    static IntPtr ownedJob;
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
        public long ProcessTime, JobTime; public uint Flags;
        public UIntPtr MinWorkingSet, MaxWorkingSet; public uint ActiveProcesses;
        public UIntPtr Affinity; public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters {
        public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
        public BasicLimits Basic; public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    public static void OwnChildren() {
        ownedJob = CreateJobObject(IntPtr.Zero, null);
        var limits = new ExtendedLimits(); limits.Basic.Flags = 0x2000; // KILL_ON_JOB_CLOSE
        int size = Marshal.SizeOf(limits); IntPtr info = Marshal.AllocHGlobal(size);
        try {
            Marshal.StructureToPtr(limits, info, false);
            if (ownedJob == IntPtr.Zero || !SetInformationJobObject(ownedJob, 9, info, (uint)size)
                || !AssignProcessToJobObject(ownedJob, Process.GetCurrentProcess().Handle))
                throw new InvalidOperationException("Cannot establish owned process lifetime");
        } finally { Marshal.FreeHGlobal(info); }
    }
    public static int[] ListeningPids(int port) {
        var found = new HashSet<int>();
        foreach (int family in new int[]{2,23}) {
            int size=0; GetExtendedTcpTable(IntPtr.Zero, ref size, false, family, 5, 0);
            IntPtr buffer=Marshal.AllocHGlobal(size);
            try {
                if (GetExtendedTcpTable(buffer, ref size, false, family, 5, 0)!=0)
                    throw new InvalidOperationException("Cannot inspect TCP ownership");
                int count=Marshal.ReadInt32(buffer); int rowSize=family==2?24:56;
                for(int i=0;i<count;i++) {
                    IntPtr row=IntPtr.Add(buffer,4+i*rowSize);
                    int state=Marshal.ReadInt32(row,family==2?0:48);
                    int offset=family==2?8:20;
                    int localPort=Marshal.ReadByte(row,offset)*256+Marshal.ReadByte(row,offset+1);
                    if(state==2 && localPort==port) found.Add(Marshal.ReadInt32(row,family==2?20:52));
                }
            } finally { Marshal.FreeHGlobal(buffer); }
        }
        var result=new int[found.Count]; found.CopyTo(result); return result;
    }
    public sealed class Child : IDisposable {
        public Process Process; FileStream output,error; Task outCopy,errCopy;
        public Child(string exe,string arguments,string cwd,string stdout,string stderr) {
            var start=new ProcessStartInfo(exe,arguments) { WorkingDirectory=cwd, UseShellExecute=false,
                CreateNoWindow=true, RedirectStandardOutput=true, RedirectStandardError=true };
            output=new FileStream(stdout,FileMode.CreateNew,FileAccess.Write,FileShare.ReadWrite);
            error=new FileStream(stderr,FileMode.CreateNew,FileAccess.Write,FileShare.ReadWrite);
            Process=System.Diagnostics.Process.Start(start);
            outCopy=Copy(Process.StandardOutput.BaseStream,output);
            errCopy=Copy(Process.StandardError.BaseStream,error);
        }
        static async Task Copy(Stream source, FileStream target) {
            byte[] buffer=new byte[4096]; int count;
            while((count=await source.ReadAsync(buffer,0,buffer.Length))>0) {
                await target.WriteAsync(buffer,0,count); await target.FlushAsync();
            }
        }
        public int Wait() {
            Process.WaitForExit(); Task.WaitAll(outCopy,errCopy);
            output.Flush(); error.Flush(); return Process.ExitCode;
        }
        public void Dispose() { output.Dispose(); error.Dispose(); Process.Dispose(); }
    }
}
