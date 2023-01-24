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
transitions = abs(diff(inData(:,1)));
[~,transitions]=findpeaks(transitions, 'MinPeakDistance', fs*0.0005,'MinPeakHeight',0.005);
for i=length(transitions):-1:2
    starts(i-1) = transitions(i-1);
    vals(i-1) = median(inData(transitions(i-1):transitions(i),1));
end
for i=length(starts):-1:1
    base = Inf;
    bj = -1;
    for j=floor(starts(i) - fs*0.0005):-1:floor(starts(i) - fs*0.0032)
        if abs(outData(j) - vals(i)) + 1e-3 < base
            bj = j;
            base = abs(outData(j) - vals(i));
        end
    end
    starts2(i) = bj;
end
disp("Latency (ms): " + string(mean(starts-starts2)/fs*1000))
%%
figure
plot((fs*1:2*fs)/fs,inData(fs*1:2*fs,1))
hold on
plot((fs*1:2*fs)/fs, outData(fs*1:2*fs))
figure
scatter(outData(2*fs:end-2*fs), inData(2*fs:end-2*fs,1),1)