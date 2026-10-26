// AGPL-3.0. Windows supervision without services, scheduled tasks or extra packages.
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Collections.Generic;
using System.ComponentModel;

public static class DshLauncherProcess {
    public static void ReplaceFile(string source,string destination) {
        File.Replace(source,destination,null);
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr attrs, string name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int type, IntPtr info, uint size);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetHandleInformation(IntPtr handle,uint mask,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFileW(string name,uint access,uint share,IntPtr attributes,uint creation,uint flags,IntPtr template);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint exitCode);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcessW(string application,System.Text.StringBuilder command,IntPtr processAttributes,IntPtr threadAttributes,bool inherit,uint flags,IntPtr environment,string cwd,ref StartupInfo startup,out ProcessInfo process);
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct StartupInfo {
        public uint Size;public string Reserved,Desktop,Title;public uint X,Y,XSize,YSize,XChars,YChars,Fill,Flags;
        public ushort Show,ReservedSize;public IntPtr ReservedData,Input,Output,Error;
    }
    [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {public IntPtr Process,Thread;public uint Pid,Tid;}
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
        public Process Process; FileStream output,error;IntPtr input;
        public Child(string exe,string arguments,string cwd,string stdout,string stderr) {
            ProcessInfo child=new ProcessInfo();bool started=false;
            try {
                output=new FileStream(stdout,FileMode.CreateNew,FileAccess.Write,FileShare.ReadWrite);
                error=new FileStream(stderr,FileMode.CreateNew,FileAccess.Write,FileShare.ReadWrite);
                input=CreateFileW("NUL",0x80000000,3,IntPtr.Zero,3,0,IntPtr.Zero);
                if(input==new IntPtr(-1))throw new Win32Exception(Marshal.GetLastWin32Error());
                foreach(var handle in new IntPtr[]{output.SafeFileHandle.DangerousGetHandle(),error.SafeFileHandle.DangerousGetHandle(),input})
                    if(!SetHandleInformation(handle,1,1))throw new Win32Exception(Marshal.GetLastWin32Error());
                var start=new StartupInfo {Size=(uint)Marshal.SizeOf(typeof(StartupInfo)),Flags=0x100,
                    Input=input,Output=output.SafeFileHandle.DangerousGetHandle(),Error=error.SafeFileHandle.DangerousGetHandle()};
                // A Store pwsh worker's Process.Start child did not inherit its
                // Job. Create suspended and explicitly assign BEFORE any user
                // instruction can run or create an unowned descendant.
                if(!CreateProcessW(exe,new System.Text.StringBuilder("\""+exe+"\" "+arguments),IntPtr.Zero,IntPtr.Zero,true,0x08000004,IntPtr.Zero,cwd,ref start,out child))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                started=true;
                if(ownedJob==IntPtr.Zero || !AssignProcessToJobObject(ownedJob,child.Process))throw new Win32Exception(Marshal.GetLastWin32Error());
                Process=System.Diagnostics.Process.GetProcessById((int)child.Pid);
                var retainedHandle=Process.Handle;
                // ResumeThread returns DWORD(-1) on failure, not BOOL.
                if(ResumeThreadCount(child.Thread)==uint.MaxValue)throw new Win32Exception(Marshal.GetLastWin32Error());
            } catch {
                if(started)TerminateProcess(child.Process,1);
                Dispose();throw;
            } finally {
                if(child.Thread!=IntPtr.Zero)CloseHandle(child.Thread);
                if(child.Process!=IntPtr.Zero)CloseHandle(child.Process);
            }
        }
        [DllImport("kernel32.dll",EntryPoint="ResumeThread",SetLastError=true)] static extern uint ResumeThreadCount(IntPtr thread);
        public int Wait() {
            Process.WaitForExit();
            output.Flush(); error.Flush(); return Process.ExitCode;
        }
        public void Dispose() { if(input!=IntPtr.Zero && input!=new IntPtr(-1)){CloseHandle(input);input=IntPtr.Zero;}if(output!=null)output.Dispose();if(error!=null)error.Dispose();if(Process!=null)Process.Dispose(); }
    }
}
