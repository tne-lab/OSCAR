%% Initialize DAQ
duration = 30;
per = 1/50;
fs=250000;
dq = daq("ni");
addinput(dq, "Dev2", "ai0", "Voltage");
addinput(dq, "Dev2", "ai1", "Voltage");
addoutput(dq, "Dev2", "ao0", "Voltage");
dq.Rate = fs;
outData = zeros(duration*fs,1);
%outData(mod(1:length(outData),fs*per)<fs*per/2)=3.3;
outData=(-cos(2*pi/per*(1:length(outData))/fs)'+1)/2*2.5;
outData=[zeros(fs,1); outData; zeros(fs,1)];
%% Start recording
inData = readwrite(dq,outData,"OutputFormat","Matrix");
outData = inData(:,2);
%%
figure
plot(outData(fs:fs*3))
hold on
plot(inData(fs:fs*3,1))
figure
scatter(outData, inData(:,1),1)
outSimp = outData(1:100:end);
inSimp = inData(1:100:end,1);
[dist,ix,iy] = dtw(outSimp,inSimp);
latency=mean(iy(2501:end-2500)-ix(2501:end-2500))/2500*1000;
error=mean(abs(outSimp(ix(2501:end-2500))-inSimp(iy(2501:end-2500))))*1000;
disp("Latency (ms): " + string(latency))
disp("Error (mV): " + string(error))