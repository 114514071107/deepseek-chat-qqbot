using System;
using System.Runtime.InteropServices;
using System.Security.Principal;
public static class RestrictedFileProbe {
 [StructLayout(LayoutKind.Sequential)] struct SID {public IntPtr Sid;public uint Attributes;}
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr p,uint a,out IntPtr t);
 [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool CreateRestrictedToken(IntPtr t,uint f,uint d,IntPtr s,uint p,IntPtr x,uint r,ref SID ids,out IntPtr n);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool ImpersonateLoggedOnUser(IntPtr t);
 [DllImport("advapi32.dll")] static extern bool RevertToSelf();
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFile(string p,uint a,uint s,IntPtr n,uint c,uint f,IntPtr t);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr p);
 public static int[] Probe(string path) {
  IntPtr original,restricted=IntPtr.Zero; if(!OpenProcessToken(GetCurrentProcess(),0xB,out original))throw new Exception("OpenToken failed");
  var sid=new SecurityIdentifier("S-1-5-12");byte[] data=new byte[sid.BinaryLength];sid.GetBinaryForm(data,0);IntPtr mem=Marshal.AllocHGlobal(data.Length);Marshal.Copy(data,0,mem,data.Length);
  try {var entry=new SID{Sid=mem,Attributes=0};if(!CreateRestrictedToken(original,1,0,IntPtr.Zero,0,IntPtr.Zero,1,ref entry,out restricted))throw new Exception("CreateRestrictedToken failed");
   if(!ImpersonateLoggedOnUser(restricted))throw new Exception("Impersonation failed");
   try {var result=new int[2];int i=0;foreach(uint access in new uint[]{0x80000000,0x40000000}) {var handle=CreateFile(path,access,7,IntPtr.Zero,3,0,IntPtr.Zero);result[i++]=handle==new IntPtr(-1)?Marshal.GetLastWin32Error():0;if(handle!=new IntPtr(-1))CloseHandle(handle);}return result;}
   finally {RevertToSelf();}
  } finally {Marshal.FreeHGlobal(mem);CloseHandle(original);if(restricted!=IntPtr.Zero)CloseHandle(restricted);}
 }
}
